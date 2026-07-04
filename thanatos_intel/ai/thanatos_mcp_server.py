#!/usr/bin/env python
"""MCP server Thanatos — espone TUTTI gli strumenti investigativi come tool MCP,
così i CLI agentici (Claude Code, Codex) hanno accesso nativo via CLI (non API).

Avvio (stdio): eseguito come subprocess dal CLI. Inizializza frappe UNA volta
sul sito thanatos, poi serve i tool tenendo il contesto caldo.

Registrazione:
  claude mcp add --scope user thanatos -- /path/to/env/bin/python /path/to/thanatos_mcp_server.py
"""
import json
import os
import sys

SITE = os.environ.get("THANATOS_SITE", "thanatos.onekeyco.com")
BENCH = os.environ.get("THANATOS_BENCH",
                       "/home/frappe/bench-cli/benches/thanatos")
SITES_PATH = os.path.join(BENCH, "sites")

# frappe scrive i log relativi alla CWD → posizionarsi nel bench root
try:
    os.chdir(BENCH)
except Exception:
    pass

import frappe  # noqa: E402


def _init():
    if getattr(frappe.local, "db", None):
        return
    frappe.init(SITE, sites_path=SITES_PATH)
    frappe.connect()
    frappe.set_user("Administrator")


def _j(x):
    return json.dumps(x, ensure_ascii=False, default=str)[:6000]


from mcp.server.fastmcp import FastMCP  # noqa: E402

# host/port per il trasporto HTTP (streamable-http). stdio resta il default.
_HOST = os.environ.get("THANATOS_MCP_HOST", "127.0.0.1")
_PORT = int(os.environ.get("THANATOS_MCP_PORT", "18099"))
mcp = FastMCP("thanatos", host=_HOST, port=_PORT)


@mcp.tool()
def stats() -> str:
    """Statistiche vive della struttura Thanatos: conteggi casi per stato,
    clienti, entità, lead, reperti + casi recenti."""
    _init()
    from thanatos_intel.ai.ops_brain import _structure_snapshot
    return _structure_snapshot()


@mcp.tool()
def global_search(query: str) -> str:
    """Cerca trasversalmente in casi, chat/lead, reperti, clienti e messaggi.
    query: testo libero (nome, P.IVA, codice caso, parola chiave)."""
    _init()
    from thanatos_intel.api.centralino import global_search as gs
    return _j(gs(query, limit=8))


@mcp.tool()
def list_cases(status: str = "") -> str:
    """Elenca i casi investigativi. status opzionale: Open|Closed|Draft|In Progress."""
    _init()
    f = {"status": status} if status else {}
    return _j(frappe.get_all("Investigation Case", filters=f,
                             fields=["name", "case_title", "status", "case_type",
                                     "priority", "client"],
                             order_by="modified desc", limit=20))


@mcp.tool()
def case_detail(case: str) -> str:
    """Dettaglio completo di un caso: reperti, attività, cliente, team, lead
    collegati. case: codice CASE-AAAA-N."""
    _init()
    from thanatos_intel.api.centralino import get_case_detail
    return _j(get_case_detail(case))


@mcp.tool()
def screening_kyc(nome: str, mode: str = "pep", case: str = "") -> str:
    """Screening reputazionale su un nominativo (persona o azienda).
    mode: pep | sanction_list | adverse_media | full. case: opzionale, per
    registrare l'esito nel fascicolo."""
    _init()
    from thanatos_intel.osint.openapi_client import screening_kyc as sk
    return _j(sk(nome, mode=mode, investigation_case=case or None))


@mcp.tool()
def soci_ubo(piva: str, case: str = "") -> str:
    """Soci e titolari effettivi (UBO) di un'impresa. piva: 11 cifre."""
    _init()
    from thanatos_intel.osint.openapi_client import soci_titolari
    return _j(soci_titolari(piva, investigation_case=case or None))


@mcp.tool()
def negativita(id: str, case: str = "") -> str:
    """Protesti e pregiudizievoli. id: codice fiscale (persona) o P.IVA (impresa)."""
    _init()
    from thanatos_intel.osint.openapi_client import negativita as neg
    return _j(neg(id, investigation_case=case or None))


@mcp.tool()
def visura(piva: str, case: str = "") -> str:
    """Visura camerale di un'impresa. piva: 11 cifre."""
    _init()
    from thanatos_intel.osint.openapi_client import visura as vis
    return _j(vis(piva, investigation_case=case or None))


@mcp.tool()
def case_tool(case: str, instruction: str) -> str:
    """Esegue uno strumento avanzato sul caso in linguaggio naturale: cluster
    societario, dossier, proforma, avanzamento/checklist, collegamenti,
    valutazione assicurativa, domande investigative. case: CASE-AAAA-N;
    instruction: cosa fare (es. 'costruisci il cluster', 'genera dossier',
    'a che punto siamo')."""
    _init()
    from thanatos_intel.ai.case_assistant import case_ai_chat
    r = case_ai_chat(case, instruction) or {}
    return _j(r)


@mcp.tool()
def run_query(sql: str) -> str:
    """Esegue una SELECT read-only sul database Thanatos (solo lettura). Utile
    per domande analitiche non coperte dagli altri strumenti."""
    _init()
    s = (sql or "").strip().rstrip(";")
    if not s.lower().startswith("select"):
        return "Solo query SELECT sono permesse."
    low = s.lower()
    if any(k in low for k in (" update ", " delete ", " insert ", " drop ",
                              " alter ", " truncate ", " into ")):
        return "Query non permessa."
    try:
        rows = frappe.db.sql(s + " LIMIT 100", as_dict=True)
        return _j(rows)
    except Exception as e:
        return f"Errore SQL: {e}"


if __name__ == "__main__":
    # THANATOS_MCP_TRANSPORT=http → servizio HTTP persistente (no spawn, no sandbox)
    # altrimenti stdio (default). init lazy in entrambi i casi.
    transport = os.environ.get("THANATOS_MCP_TRANSPORT", "stdio")
    if transport in ("http", "streamable-http"):
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
