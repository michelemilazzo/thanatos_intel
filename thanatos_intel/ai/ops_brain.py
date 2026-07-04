"""Cervello operativo globale Thanatos — assistente AI agentico con accesso
a TUTTA la struttura (casi, entità, clienti, lead, reperti, statistiche) e a
TUTTI gli strumenti (screening KYC/PEP/sanzioni, soci/UBO, negatività,
patrimoniale, visure, cluster societari, dossier, proforma, avanzamento caso…).

Non è un chatbot scriptato: il modello riceve un catalogo di TOOL e un
riassunto vivo della struttura, decide se rispondere direttamente o invocare
uno strumento (JSON), noi lo eseguiamo e gli ridiamo l'esito per la risposta
finale. Usato sia da WhatsApp (operatore) sia dal pannello AI della Switchboard.
"""
import json
import os
import re
import frappe


# ─────────────────────────── snapshot struttura ──────────────────────────────

def _structure_snapshot():
    """Riassunto vivo dello stato: conteggi, casi recenti, entità/clienti."""
    def count(dt, filters=None):
        try:
            return frappe.db.count(dt, filters or {})
        except Exception:
            return 0
    parts = []
    by_status = frappe.db.sql(
        "SELECT status, COUNT(*) n FROM `tabInvestigation Case` GROUP BY status",
        as_dict=True)
    status_line = ", ".join(f"{r['status'] or '?'}: {r['n']}" for r in by_status)
    parts.append(f"Casi totali: {count('Investigation Case')} ({status_line}).")
    parts.append(f"Clienti: {count('Investigation Client')} · "
                 f"Entità: {count('Investigation Entity')} · "
                 f"Lead: {count('Intel Lead')} · "
                 f"Reperti: {count('Investigation Evidence')}.")
    recent = frappe.get_all("Investigation Case",
                            fields=["name", "case_title", "status", "case_type"],
                            order_by="modified desc", limit=8)
    if recent:
        parts.append("Casi recenti:\n" + "\n".join(
            f"- {c.name} [{c.status}] {c.case_type or ''}: {c.case_title or ''}"
            for c in recent))
    return "\n".join(parts)


# ─────────────────────────────── strumenti ───────────────────────────────────

def _t_global_search(q=None, **kw):
    from thanatos_intel.api.centralino import global_search
    r = global_search(q or "", limit=8)
    out = {}
    for k, v in r.items():
        if v:
            out[k] = v
    return out or {"info": "nessun risultato"}


def _t_list_cases(status=None, **kw):
    filters = {}
    if status:
        filters["status"] = status
    return frappe.get_all("Investigation Case", filters=filters,
                          fields=["name", "case_title", "status", "case_type",
                                  "priority", "client"],
                          order_by="modified desc", limit=15)


def _t_case_detail(case=None, **kw):
    if not case:
        return {"error": "manca il codice caso"}
    from thanatos_intel.api.centralino import get_case_detail
    try:
        return get_case_detail(case)
    except Exception as e:
        return {"error": str(e)}


def _t_stats(**kw):
    return {"snapshot": _structure_snapshot()}


def _t_screening_kyc(nome=None, mode="pep", case=None, **kw):
    if not nome:
        return {"error": "manca il nominativo"}
    from thanatos_intel.osint.openapi_client import screening_kyc
    return screening_kyc(nome, mode=mode, investigation_case=case)


def _t_soci_ubo(piva=None, case=None, **kw):
    if not piva:
        return {"error": "manca la P.IVA"}
    from thanatos_intel.osint.openapi_client import soci_titolari
    return soci_titolari(piva, investigation_case=case)


def _t_negativita(id=None, case=None, **kw):
    if not id:
        return {"error": "manca CF o P.IVA"}
    from thanatos_intel.osint.openapi_client import negativita
    return negativita(id, investigation_case=case)


def _t_visura(piva=None, case=None, **kw):
    if not piva:
        return {"error": "manca la P.IVA"}
    from thanatos_intel.osint.openapi_client import visura
    return visura(piva, investigation_case=case)


def _t_case_tool(case=None, instruction=None, **kw):
    """Delega all'assistente del caso (esegue lo strumento reale: cluster,
    dossier, proforma, avanzamento, collegamenti, assicurazione…)."""
    if not case or not instruction:
        return {"error": "servono case e instruction"}
    from thanatos_intel.ai.case_assistant import case_ai_chat
    return case_ai_chat(case, instruction)


TOOLS = {
    "global_search": _t_global_search,   # {q}
    "list_cases": _t_list_cases,          # {status?}
    "case_detail": _t_case_detail,        # {case}
    "stats": _t_stats,                    # {}
    "screening_kyc": _t_screening_kyc,    # {nome, mode: pep|sanction_list|adverse_media|full}
    "soci_ubo": _t_soci_ubo,              # {piva}
    "negativita": _t_negativita,          # {id}
    "visura": _t_visura,                  # {piva}
    "case_tool": _t_case_tool,            # {case, instruction}  → cluster/dossier/proforma/…
}

_TOOL_DOC = """STRUMENTI (rispondi con JSON {"tool":"nome","args":{...}} per usarne uno):
- global_search {q}: cerca in casi, chat, reperti, clienti, messaggi
- list_cases {status?}: elenca casi (status: Open|Closed|…)
- case_detail {case}: dettaglio caso (reperti, attività, cliente, team)
- stats {}: statistiche struttura (conteggi, casi recenti)
- screening_kyc {nome, mode}: PEP/sanzioni/adverse media su un nominativo (mode: pep|sanction_list|adverse_media|full)
- soci_ubo {piva}: soci e titolari effettivi di un'impresa (P.IVA 11 cifre)
- negativita {id}: protesti/pregiudizievoli (CF persona o P.IVA impresa)
- visura {piva}: visura camerale impresa
- case_tool {case, instruction}: esegue sul caso strumenti avanzati — cluster societario, dossier, proforma, avanzamento/checklist, collegamenti, valutazione assicurativa. Passa l'istruzione in linguaggio naturale.
"""

_SYS = (
    "Sei il cervello operativo di Thanatos Intel, agenzia investigativa (sede "
    "Romania, GDPR/Legea 329-2003). Parli con un OPERATORE interno su WhatsApp: "
    "dagli del tu, tono diretto e concreto, niente disclaimer commerciali. "
    "Conosci TUTTA la struttura e hai accesso a strumenti reali.\n\n"
    + _TOOL_DOC +
    "\nREGOLE:\n"
    "- Se per rispondere serve un dato o un'azione, USA uno strumento: rispondi "
    "SOLO con il JSON {\"tool\":...,\"args\":{...}}, nient'altro.\n"
    "- Se hai già abbastanza per rispondere (o è una domanda generica), rispondi "
    "in testo normale, breve e operativo (max ~140 parole).\n"
    "- Quando citi un caso usa il codice CASE-AAAA-N. Non inventare dati: se non "
    "ce l'hai, usa lo strumento giusto o dillo.\n"
)


def _resp_text(resp):
    from thanatos_intel.ai.case_architect import _resp_text as rt
    return rt(resp)


def _extract_toolcall(text):
    """Prova a estrarre un JSON {tool, args} dalla risposta del modello."""
    if not text:
        return None
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
        if m:
            t = m.group(1).strip()
    if not t.startswith("{"):
        m = re.search(r"\{.*\}", t, re.DOTALL)
        if not m:
            return None
        t = m.group(0)
    try:
        d = json.loads(t)
    except Exception:
        return None
    if isinstance(d, dict) and d.get("tool") in TOOLS:
        return d
    return None


# ─────────────────────── motore CLI (Claude Code / Codex) ────────────────────

_MCP_TOOLS = [
    "mcp__thanatos__stats", "mcp__thanatos__global_search",
    "mcp__thanatos__list_cases", "mcp__thanatos__case_detail",
    "mcp__thanatos__screening_kyc", "mcp__thanatos__soci_ubo",
    "mcp__thanatos__negativita", "mcp__thanatos__visura",
    "mcp__thanatos__case_tool", "mcp__thanatos__run_query",
]

_CLI_SYS = (
    "Sei il cervello operativo di Thanatos Intel, agenzia investigativa (sede "
    "Romania, GDPR/Legea 329-2003). Parli con un OPERATORE interno: dagli del tu, "
    "tono diretto e concreto, niente disclaimer. Hai gli strumenti MCP thanatos "
    "(stats, global_search, list_cases, case_detail, screening_kyc, soci_ubo, "
    "negativita, visura, case_tool, run_query): USALI per rispondere con dati "
    "reali invece di inventare. Risposte brevi e operative, in italiano. Quando "
    "citi un caso usa il codice CASE-AAAA-N. Non chiedere conferme: agisci."
)


def _cli_answer(text, operator=None, ctx_case=None, session_id=None):
    """Interroga il cervello via Claude Code CLI + MCP thanatos (tutti gli
    strumenti). Ritorna il testo, o None se il CLI non è disponibile."""
    import subprocess
    claude = frappe.conf.get("ops_brain_claude_bin") or "/usr/local/bin/claude"
    if not os.path.exists(claude):
        return None
    prompt = text if not ctx_case else f"[Caso di contesto: {ctx_case}] {text}"
    cmd = [claude, "-p", prompt,
           "--append-system-prompt", _CLI_SYS,
           "--allowedTools", *_MCP_TOOLS,
           "--output-format", "text"]
    env = dict(os.environ)
    env["HOME"] = frappe.conf.get("ops_brain_home") or "/home/frappe"
    env["THANATOS_SITE"] = frappe.local.site or "thanatos.onekeyco.com"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=170, env=env)
        out = (r.stdout or "").strip()
        return out or None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain cli")
        return None


def _codex_answer(text, operator=None, ctx_case=None):
    """Motore alternativo: Codex CLI su ai-core (via SSH) con MCP thanatos.
    Attivo solo se site_config `ops_brain_codex_ssh` è valorizzato
    (es. '-i /home/frappe/.ssh/ai_core root@10.10.0.4'). Codex usa l'MCP
    thanatos raggiungibile dalla rete privata."""
    import shlex
    import subprocess
    ssh_target = frappe.conf.get("ops_brain_codex_ssh")
    if not ssh_target:
        return None
    prompt = text if not ctx_case else f"[Caso di contesto: {ctx_case}] {text}"
    full = (_CLI_SYS + "\n\nRichiesta operatore: " + prompt)
    remote = "codex exec --skip-git-repo-check " + shlex.quote(full)
    cmd = ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
           *shlex.split(ssh_target), remote]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=175)
        out = (r.stdout or "").strip()
        # codex exec stampa header + "codex\n<risposta>\ntokens used…" → estrai il corpo
        if "codex\n" in out:
            body = out.split("codex\n", 1)[1]
            body = re.split(r"\ntokens used", body)[0].strip()
            return body or None
        return out or None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain codex")
        return None


def answer(text, operator=None, lead_name=None, session_id=None, max_steps=3):
    """Cervello operativo. Motore selezionabile via site_config `ops_brain_engine`:
      cli (default) = Claude Code CLI + MCP; codex = Codex CLI su ai-core + MCP;
      gateway = ciclo agentico su gateway MMOS AI. Ogni motore ha fallback al
      successivo se non disponibile."""
    from thanatos_intel.ai.doc_ingest import _gateway

    # caso di contesto (se la chat è agganciata o citato nel testo)
    ctx_case = None
    if lead_name:
        ctx_case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    m = re.search(r"CASE-\d{4}-\d+", text or "", re.I)
    if m and frappe.db.exists("Investigation Case", m.group(0).upper()):
        ctx_case = m.group(0).upper()

    engine = frappe.conf.get("ops_brain_engine", "cli")

    # 1) motore selezionato (con fallback in cascata)
    if engine == "codex":
        cx = _codex_answer(text, operator=operator, ctx_case=ctx_case)
        if cx:
            return cx
        # fallback a claude cli
        cli = _cli_answer(text, operator=operator, ctx_case=ctx_case,
                          session_id=session_id)
        if cli:
            return cli
    elif engine != "gateway":  # "cli" (default) o qualsiasi altro
        cli = _cli_answer(text, operator=operator, ctx_case=ctx_case,
                          session_id=session_id)
        if cli:
            return cli
        # fallback a codex se configurato
        cx = _codex_answer(text, operator=operator, ctx_case=ctx_case)
        if cx:
            return cx

    # 2) fallback finale: ciclo agentico su gateway
    sid = session_id or f"opsbrain-{operator or 'x'}"
    snapshot = _structure_snapshot()
    convo = (f"Contesto struttura (aggiornato):\n{snapshot}\n"
             + (f"\nCaso di contesto attuale: {ctx_case}\n" if ctx_case else "")
             + f"\nRichiesta operatore: «{text}»")

    for step in range(max_steps):
        resp = _gateway(convo, system=_SYS, task_type="chat", session_id=sid)
        out = (_resp_text(resp) or "").strip()
        _meter(resp, lead_name)
        if not out:
            return "Assistente AI momentaneamente non disponibile."
        call = _extract_toolcall(out)
        if not call:
            return out  # risposta finale in testo
        # esegui lo strumento
        tool = call["tool"]
        args = call.get("args") or {}
        if ctx_case and "case" not in args and tool in ("case_detail", "case_tool",
                                                          "screening_kyc", "soci_ubo",
                                                          "negativita", "visura"):
            args.setdefault("case", ctx_case)
        try:
            result = TOOLS[tool](**args)
        except Exception as e:
            result = {"error": str(e)}
        # ridai l'esito al modello per la risposta finale
        convo = (f"Ho eseguito lo strumento «{tool}» con args {json.dumps(args, ensure_ascii=False)}.\n"
                 f"Risultato:\n{json.dumps(result, ensure_ascii=False, default=str)[:3500]}\n\n"
                 "Ora rispondi all'operatore in testo, breve e operativo. "
                 "Se serve un altro strumento, richiamalo col JSON.")
    # esaurito il budget di step → ultima risposta testuale
    return out if not _extract_toolcall(out) else "Ho raccolto i dati ma non sono riuscito a sintetizzarli — riprova più specifico."


def _meter(resp, ref):
    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=None, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0),
                         tokens_out=usage.get("tokens_out", 0), reference=ref)
    except Exception:
        pass


@frappe.whitelist()
def ask(message, session_id=None):
    """Endpoint per il pannello AI della Switchboard (web)."""
    if frappe.session.user == "Guest":
        frappe.throw("Login richiesto")
    reply = answer(message, operator=frappe.session.user, session_id=session_id)
    return {"reply": reply}
