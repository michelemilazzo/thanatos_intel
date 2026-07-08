"""Proxy MCP wallet-gated davanti all'MCP openapi ufficiale.

Flusso:  Cervello (Claude) -> :18101 (questo proxy) -> :18100 (MCP openapi) -> openapi

Su ogni JSON-RPC `tools/call`:
  1) chiede a `thanatos_intel.ai.openapi_gate.check(tool)` se c'e' saldo wallet MMOS;
  2) se NON ok -> risponde subito con errore JSON-RPC (nessuna richiesta a openapi);
  3) se ok -> inoltra all'MCP openapi in streaming; a status 200 chiama `openapi_gate.charge(tool)`.

Tutti gli altri metodi (initialize, tools/list, notifications, ping, GET SSE) passano
trasparenti senza gate. Streaming async (httpx + starlette) per non rompere il transport
streamable-http/SSE. Gira col venv openapi (starlette+httpx+uvicorn), NON importa frappe:
il gate e' raggiunto via HTTP interno (thanatos web :8001), protetto da token condiviso.
"""
import os
import json
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, StreamingResponse

UPSTREAM = os.environ.get("GATE_UPSTREAM", "http://127.0.0.1:18100")
GATE_BASE = os.environ.get("GATE_FRAPPE_URL",
                           "http://127.0.0.1:8001/api/method/thanatos_intel.ai.openapi_gate")
GATE_HOST = os.environ.get("GATE_FRAPPE_HOST", "thanatos.onekeyco.com")
TOKEN = os.environ.get("OPENAPI_GATE_TOKEN", "")
# 'sandbox' => gate in passthrough (openapi gratuito); 'prod' => gate attivo su saldo wallet.
MODE = os.environ.get("GATE_MODE", "prod")

_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0))
_gate_client = httpx.AsyncClient(timeout=httpx.Timeout(20.0))


async def _gate(fn, params):
    try:
        r = await _gate_client.post("%s.%s" % (GATE_BASE, fn), json=params,
                                    headers={"Host": GATE_HOST})
        return (r.json() or {}).get("message") or {}
    except Exception as e:  # gate irraggiungibile => fail-closed sui pagamenti
        return {"ok": False, "reason": "gate non raggiungibile: %s" % e}


async def handler(request):
    body = await request.body()
    method = tool = rid = None
    if body:
        try:
            j = json.loads(body)
            method = j.get("method")
            rid = j.get("id")
            if method == "tools/call":
                tool = (j.get("params") or {}).get("name")
        except Exception:
            pass

    # GATE pre-flight solo su tools/call
    if method == "tools/call" and tool:
        g = await _gate("check", {"tool": tool, "token": TOKEN, "mode": MODE})
        if not g.get("ok"):
            return JSONResponse({
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32003, "message": "GATE spesa MMOS bloccato: %s"
                          % g.get("reason", "saldo insufficiente / non autorizzato")},
            })

    # Inoltro upstream (streaming)
    fwd_headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in ("host", "content-length", "accept-encoding")}
    up_req = _client.build_request(request.method, UPSTREAM + request.url.path,
                                   content=body if body else None,
                                   headers=fwd_headers, params=request.query_params)
    up = await _client.send(up_req, stream=True)

    # Addebito dopo successo upstream (solo tool a pagamento)
    if tool and up.status_code == 200:
        await _gate("charge", {"tool": tool, "token": TOKEN, "ref": str(rid or ""), "mode": MODE})

    async def relay():
        try:
            async for chunk in up.aiter_raw():
                yield chunk
        finally:
            await up.aclose()

    resp_headers = {k: v for k, v in up.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding",
                                         "content-encoding", "connection")}
    return StreamingResponse(relay(), status_code=up.status_code, headers=resp_headers,
                             media_type=up.headers.get("content-type"))


app = Starlette(routes=[
    Route("/{path:path}", handler, methods=["GET", "POST", "DELETE", "OPTIONS"]),
])
