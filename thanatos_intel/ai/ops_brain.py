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

_VAULT = "/home/frappe/.secrets/integrations.json"


def _vault(field, integration="ai_engines"):
    """Legge un campo dal vault segreti admin (fonte unica di chiavi/password).
    Struttura: {integration:{fields:{field:{value}}}}. Ritorna None se assente."""
    try:
        return (json.load(open(_VAULT))[integration]["fields"][field]["value"]) or None
    except Exception:
        return None


def _secret(field, conf_key):
    """Chiave con priorità: vault admin → site_config (retrocompat)."""
    return _vault(field) or frappe.conf.get(conf_key)


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


def _t_list_documents(case=None, lead=None, **kw):
    """Elenca TUTTI i file allegati a un caso o lead (anche quelli non ancora
    ingeriti come reperti), con stato. Serve al cervello per vedere i documenti
    che l'operatore ha appena mandato, prima che siano processati."""
    docs = []
    if case:
        for f in frappe.get_all("File",
                filters={"attached_to_doctype": "Investigation Case",
                         "attached_to_name": case},
                fields=["file_name", "file_url"], limit=0):
            docs.append({"file": f.file_name, "url": f.file_url, "stato": "allegato (non ingerito)"})
        for e in frappe.get_all("Investigation Evidence",
                filters={"investigation_case": case},
                fields=["evidence_name", "attached_file", "notes"], limit=0):
            docs.append({"file": e.evidence_name, "url": e.attached_file,
                         "stato": "reperto ingerito" if (e.notes and "Sintesi" in (e.notes or "")) else "reperto (senza sintesi)"})
    if lead:
        for f in frappe.get_all("File",
                filters={"attached_to_doctype": "Intel Lead",
                         "attached_to_name": lead},
                fields=["file_name", "file_url"], limit=0):
            docs.append({"file": f.file_name, "url": f.file_url, "stato": "allegato chat"})
    return {"count": len(docs), "documents": docs}


def _t_read_document(file_url=None, **kw):
    """Legge/OCR il contenuto testuale COMPLETO di un documento on-demand (PDF,
    immagine, docx…). Usa questo per analizzare un allegato che non è ancora un
    reperto sintetizzato."""
    if not file_url:
        return {"error": "manca file_url"}
    from thanatos_intel.ai.doc_ingest import _read_text_fallback
    text = ""
    try:
        from thanatos_intel.ai.ocr_service import ocr_file
        r = ocr_file(file_url, "generic") or {}
        text = (r.get("raw_text") or "").strip()
    except Exception:
        pass
    if not text:
        try:
            text = (_read_text_fallback(file_url) or "").strip()
        except Exception:
            text = ""
    return {"file_url": file_url,
            "text": text[:8000] if text else "(documento vuoto o illeggibile)"}


def _t_ingest_document(case=None, file_url=None, **kw):
    """Ingerisce un documento allegato come REPERTO del caso (OCR + estrazione AI
    + hash catena di custodia). Usa dopo che l'operatore ha mandato un file e
    vuole che diventi parte del fascicolo."""
    if not (case and file_url):
        return {"error": "servono case e file_url"}
    from thanatos_intel.ai.doc_ingest import ingest_document
    try:
        r = ingest_document(file_url=file_url, investigation_case=case,
                            document_type="generic") or {}
    except Exception as e:
        return {"error": str(e)}
    ex = r.get("extracted") or {}
    return {"ok": True, "summary": ex.get("summary", ""),
            "authenticity": r.get("authenticity"),
            "evidence": r.get("evidence"),
            "risk_flags": ex.get("risk_flags") or []}


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
    "list_documents": _t_list_documents,  # {case?, lead?} → file allegati (anche non ingeriti)
    "read_document": _t_read_document,    # {file_url} → testo OCR completo on-demand
    "ingest_document": _t_ingest_document,  # {case, file_url} → reperto (OCR+AI+hash)
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
- list_documents {case?, lead?}: elenca TUTTI i file allegati a un caso o lead, anche quelli non ancora ingeriti come reperti (i documenti che l'operatore ha appena mandato)
- read_document {file_url}: legge/OCR il testo completo di un documento on-demand (per analizzare un allegato non ancora sintetizzato)
- ingest_document {case, file_url}: ingerisce un allegato come reperto del caso (OCR + estrazione AI + hash catena di custodia)
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
    "mcp__thanatos__list_documents", "mcp__thanatos__read_document",
    "mcp__thanatos__ingest_document",
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


# ─────────────────────────── metering / billing ─────────────────────────────

def _track(engine, model, tin=0, tout=0):
    """Registra (per-richiesta, thread-safe) motore+token per la fatturazione."""
    frappe.local._ob_meter = {"engine": engine, "model": model,
                              "tin": int(tin or 0), "tout": int(tout or 0)}


def _bill_last(reference=None, client=None):
    """Fattura l'ultima richiesta a €0.03/1000 token (MMOS→Thanatos). Registra su
    AI Usage Log con motore, modello, token, costo. Rate override:
    site_config ops_brain_bill_rate (EUR per 1000 token)."""
    m = getattr(frappe.local, "_ob_meter", None)
    if not m:
        return
    frappe.local._ob_meter = None
    rate = float(frappe.conf.get("ops_brain_bill_rate") or 0.03)  # EUR / 1000 token
    total = m["tin"] + m["tout"]
    client_cost = round(total / 1000.0 * rate, 6)
    # se non abbiamo token (CLI senza usage), forfait minimo per non perdere revenue
    if total == 0:
        client_cost = round(float(frappe.conf.get("ops_brain_bill_min") or 0.01), 6)
    # provider = valore valido del Select AI Usage Log; motore/modello nel campo model
    provider = _PROVIDER.get(m["engine"], "Other")
    model_label = f"{m['engine']}/{m['model']}"
    try:
        frappe.get_doc({
            "doctype": "AI Usage Log", "client": client,
            "provider": provider, "model": model_label,
            "tokens_in": m["tin"], "tokens_out": m["tout"],
            "real_cost": 0, "client_cost": client_cost,
            "reference": reference, "usage_date": frappe.utils.nowdate(),
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain bill")
    return client_cost


# motore ops_brain → provider valido (Select di AI Usage Log)
_PROVIDER = {
    "opencode-zen": "OpenCode", "claude": "Anthropic", "codex": "OpenAI",
    "openrouter": "OpenRouter", "gateway": "Other", "ollama": "Other",
}


def _ctx_prefix(ctx_case=None, lead=None):
    """Nota di contesto da anteporre al prompt: caso e/o lead con gli allegati."""
    parts = []
    if ctx_case:
        parts.append(f"Caso di contesto: {ctx_case}")
    if lead:
        parts.append(f"Lead/chat corrente: {lead}. I documenti che l'operatore "
                     f"ha appena allegato sono qui: usa list_documents(lead=\"{lead}\") "
                     f"per vederli e read_document(file_url) per leggerli")
    return f"[{'; '.join(parts)}] " if parts else ""


def _cli_answer(text, operator=None, ctx_case=None, session_id=None, lead=None):
    """Interroga il cervello via Claude Code CLI + MCP thanatos (tutti gli
    strumenti). Ritorna il testo, o None se il CLI non è disponibile."""
    import json as _json
    import subprocess
    claude = frappe.conf.get("ops_brain_claude_bin") or "/usr/local/bin/claude"
    if not os.path.exists(claude):
        return None
    prompt = _ctx_prefix(ctx_case, lead) + text
    cmd = [claude, "-p", prompt,
           "--append-system-prompt", _CLI_SYS,
           "--allowedTools", *_MCP_TOOLS,
           "--output-format", "json"]
    env = dict(os.environ)
    env["HOME"] = frappe.conf.get("ops_brain_home") or "/home/frappe"
    env["THANATOS_SITE"] = frappe.local.site or "thanatos.onekeyco.com"
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=170, env=env)
        raw = (r.stdout or "").strip()
        if not raw:
            return None
        try:
            d = _json.loads(raw)
        except Exception:
            return raw  # output text non-json: usalo comunque
        if d.get("is_error"):
            return None
        out = (d.get("result") or "").strip()
        if not out or "Not logged in" in out:
            return None
        u = d.get("usage") or {}
        tin = int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0))
        _track("claude", d.get("modelUsage") and next(iter(d["modelUsage"]), "claude") or "claude",
               tin, int(u.get("output_tokens", 0)))
        return out
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain cli")
        return None


def _codex_answer(text, operator=None, ctx_case=None, lead=None):
    """Motore alternativo: Codex CLI su ai-core (via SSH) con MCP thanatos.
    Attivo solo se site_config `ops_brain_codex_ssh` è valorizzato
    (es. '-i /home/frappe/.ssh/ai_core root@10.10.0.4'). Codex usa l'MCP
    thanatos raggiungibile dalla rete privata."""
    import shlex
    import subprocess
    ssh_target = frappe.conf.get("ops_brain_codex_ssh")
    if not ssh_target:
        return None
    prompt = _ctx_prefix(ctx_case, lead) + text
    full = (_CLI_SYS + "\n\nRichiesta operatore: " + prompt)
    # workdir codex trusted + flag opzionale per abilitare i tool MCP headless
    workdir = frappe.conf.get("ops_brain_codex_workdir") or "/root/thanatos-brain"
    port = int(frappe.conf.get("ops_brain_mcp_port") or 18099)
    flags = "--skip-git-repo-check"
    if frappe.conf.get("ops_brain_codex_bypass"):
        # necessario perché codex headless annulla le chiamate MCP senza questo
        flags += " --dangerously-bypass-approvals-and-sandbox"
    remote = (f"cd {shlex.quote(workdir)} && codex exec {flags} "
              + shlex.quote(full))
    # tunnel SSH inverso: l'MCP resta su 127.0.0.1 di dev, codex lo raggiunge
    # su ai-core solo durante la chiamata (nessuna esposizione di rete).
    cmd = ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes",
           "-o", "StrictHostKeyChecking=accept-new",
           "-R", f"{port}:127.0.0.1:{port}"]
    key = frappe.conf.get("ops_brain_codex_key")
    if key:
        cmd += ["-i", key]
    cmd += [ssh_target, remote]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=175)
        out = (r.stdout or "").strip()
        # token: codex stampa "tokens used\n<N>"
        tm = re.search(r"tokens used\s*\n?\s*([\d,]+)", out)
        toks = int(tm.group(1).replace(",", "")) if tm else 0
        _track("codex", "codex-gpt", 0, toks)
        # codex exec stampa header + "codex\n<risposta>\ntokens used…" → estrai il corpo
        if "codex\n" in out:
            body = out.split("codex\n", 1)[1]
            body = re.split(r"\ntokens used", body)[0].strip()
            return body or None
        return out or None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain codex")
        return None


# ─────────────── motori economici: Ollama (gratis) + OpenRouter ───────────────

def _ollama_chat(convo, system):
    """LLM callable su Ollama locale (ai-core, gratis). Ritorna (testo, usage)."""
    import requests
    url = (frappe.conf.get("ops_brain_ollama_url")
           or "http://10.10.0.4:11434").rstrip("/")
    model = frappe.conf.get("ops_brain_ollama_model") or "qwen2.5:7b"
    try:
        r = requests.post(f"{url}/api/chat", json={
            "model": model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": convo}],
            "options": {"temperature": 0.2},
        }, timeout=120)
        r.raise_for_status()
        d = r.json()
        return (d.get("message", {}).get("content", "") or "").strip(), {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain ollama")
        return "", {}


def _cheap_chat(convo, system):
    """LLM callable su un endpoint OpenAI-compatibile economico (default OpenCode
    Zen, modello free tool-capable). Configurabile: ops_brain_cheap_url/key/model.
    Fallback storico: openrouter_api_key."""
    import requests
    url = (_secret("cheap_url", "ops_brain_cheap_url")
           or "https://opencode.ai/zen/v1/chat/completions")
    key = (_secret("cheap_key", "ops_brain_cheap_key")
           or _secret("openrouter_api_key", "openrouter_api_key"))
    if not key:
        return "", {}
    model = _secret("cheap_model", "ops_brain_cheap_model") or "deepseek-v4-flash-free"
    try:
        r = requests.post(url,
            headers={"Authorization": f"Bearer {key}",
                     "HTTP-Referer": "https://thanatos.agency",
                     "X-Title": "Thanatos Ops Brain",
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": convo}],
                  "temperature": 0.2},
            timeout=120)
        r.raise_for_status()
        d = r.json()
        txt = (d.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
        return txt, (d.get("usage") or {})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain cheap")
        return "", {}


def _agentic_loop(text, ctx_case, llm_fn, lead_name=None, max_steps=3,
                  label="cheap", model="ext"):
    """Ciclo agentico riusabile: il modello (llm_fn) riceve snapshot+catalogo,
    emette {tool,args} JSON che eseguiamo, poi risponde. llm_fn(convo, system)
    → (testo, usage). Accumula i token di tutti gli step e traccia il motore per
    la fatturazione. Ritorna la risposta finale o None se il modello non parla."""
    snapshot = _structure_snapshot()
    lead_note = ""
    if lead_name:
        lead_note = (f"\nLead/chat corrente: {lead_name}. I file appena allegati "
                     f"dall'operatore sono qui: usa list_documents(lead=\"{lead_name}\") "
                     f"per vederli e read_document(file_url) per leggerli.\n")
    convo = (f"Contesto struttura (aggiornato):\n{snapshot}\n"
             + (f"\nCaso di contesto attuale: {ctx_case}\n" if ctx_case else "")
             + lead_note
             + f"\nRichiesta operatore: «{text}»")
    out = ""
    tot_in = tot_out = 0
    for _step in range(max_steps):
        out, usage = llm_fn(convo, _SYS)
        out = (out or "").strip()
        if usage:
            tot_in += int(usage.get("prompt_tokens") or usage.get("prompt_eval_count")
                          or usage.get("tokens_in") or 0)
            tot_out += int(usage.get("completion_tokens") or usage.get("eval_count")
                           or usage.get("tokens_out") or 0)
        if not out:
            return None
        call = _extract_toolcall(out)
        if not call:
            _track(label, model, tot_in, tot_out)
            return out
        tool = call["tool"]
        args = call.get("args") or {}
        if ctx_case and "case" not in args and tool in (
                "case_detail", "case_tool", "screening_kyc", "soci_ubo",
                "negativita", "visura", "list_documents", "ingest_document"):
            args.setdefault("case", ctx_case)
        try:
            result = TOOLS[tool](**args)
        except Exception as e:
            result = {"error": str(e)}
        convo = (f"Ho eseguito lo strumento «{tool}» con args "
                 f"{json.dumps(args, ensure_ascii=False)}.\nRisultato:\n"
                 f"{json.dumps(result, ensure_ascii=False, default=str)[:3500]}\n\n"
                 "Ora rispondi all'operatore in testo, breve e operativo. "
                 "Se serve un altro strumento, richiamalo col JSON.")
    if out and not _extract_toolcall(out):
        _track(label, model, tot_in, tot_out)
        return out
    return None


# domande "semplici" (saluti, generiche) che non richiedono i tool investigativi
_SIMPLE_RE = re.compile(
    r"^\s*(ciao|salve|buongiorno|buonasera|grazie|ok|come stai|"
    r"chi sei|cosa sai fare|aiuto|help|test)\b", re.I)


def answer(text, operator=None, lead_name=None, session_id=None, max_steps=3):
    """Cervello operativo. Motore via site_config `ops_brain_engine`:
      auto    = router a costi scalati (ollama gratis per semplice/economico →
                openrouter economico → claude per il complesso)
      cli     = Claude Code CLI + MCP (default)
      codex   = Codex CLI su ai-core + MCP
      ollama  = ciclo agentico su Ollama locale (gratis)
      openrouter = ciclo agentico su OpenRouter (economico)
      gateway = ciclo agentico su gateway MMOS AI
    Ogni motore cade sul successivo se non risponde."""
    # caso di contesto (se la chat è agganciata o citato nel testo)
    ctx_case = None
    if lead_name:
        ctx_case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    m = re.search(r"CASE-\d{4}-\d+", text or "", re.I)
    if m and frappe.db.exists("Investigation Case", m.group(0).upper()):
        ctx_case = m.group(0).upper()

    engine = frappe.conf.get("ops_brain_engine", "cli")

    # helper: catena di fallback finché uno risponde
    def _chain(*fns):
        for fn in fns:
            r = fn()
            if r:
                return r
        return None

    cheap_model = frappe.conf.get("ops_brain_cheap_model") or "deepseek-v4-flash-free"
    ollama_model = frappe.conf.get("ops_brain_ollama_model") or "qwen2.5:7b"
    E_claude = lambda: _cli_answer(text, operator=operator, ctx_case=ctx_case,
                                   session_id=session_id, lead=lead_name)
    E_codex = lambda: _codex_answer(text, operator=operator, ctx_case=ctx_case, lead=lead_name)
    E_ollama = lambda: _agentic_loop(text, ctx_case, _ollama_chat, lead_name,
                                     max_steps, label="ollama", model=ollama_model)
    E_cheap = lambda: (_agentic_loop(text, ctx_case, _cheap_chat, lead_name,
                                     max_steps, label="opencode-zen", model=cheap_model)
                       if (_secret("cheap_key", "ops_brain_cheap_key")
                           or _secret("openrouter_api_key", "openrouter_api_key")) else None)
    E_gw = lambda: _gateway_answer(text, ctx_case, lead_name, session_id, operator, max_steps)

    # Router a costi scalati. cheap (OpenCode Zen free) è il workhorse; Claude è
    # l'escalation per il complesso; Codex/gateway alternative; Ollama (CPU,
    # lento) ultimo fallback offline.
    if engine == "auto":
        r = _chain(E_cheap, E_claude, E_codex, E_gw, E_ollama)
    elif engine == "codex":
        r = _chain(E_codex, E_claude, E_gw)
    elif engine == "ollama":
        r = _chain(E_ollama, E_claude, E_gw)
    elif engine == "openrouter":
        r = _chain(E_cheap, E_ollama, E_claude, E_gw)
    elif engine == "gateway":
        r = _chain(E_gw, E_claude)
    else:  # cli (default)
        r = _chain(E_claude, E_codex, E_cheap, E_ollama, E_gw)

    # fatturazione MMOS→Thanatos a €0.03/1000 token del motore che ha risposto
    _bill_last(reference=lead_name)
    return r or "Assistente AI momentaneamente non disponibile."


def _gateway_answer(text, ctx_case, lead_name, session_id, operator, max_steps):
    """Ciclo agentico sul gateway MMOS AI (fallback storico)."""
    from thanatos_intel.ai.doc_ingest import _gateway
    sid = session_id or f"opsbrain-{operator or 'x'}"

    def _gw_fn(convo, system):
        resp = _gateway(convo, system=system, task_type="chat", session_id=sid)
        return (_resp_text(resp) or ""), ((resp or {}).get("usage") or {})

    return _agentic_loop(text, ctx_case, _gw_fn, lead_name, max_steps,
                         label="gateway", model="mmos-gateway")


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


STAFF_ROLES = {"System Manager", "Investigation Manager", "Investigator",
               "Thanatos Investigator", "Thanatos Supervisor",
               "Thanatos Director", "Thanatos Analyst"}


def _require_staff():
    if frappe.session.user == "Guest":
        frappe.throw("Login richiesto")
    if not STAFF_ROLES & set(frappe.get_roles()):
        frappe.throw("Riservato allo staff Thanatos", frappe.PermissionError)


@frappe.whitelist()
def ask(message, session_id=None):
    """Endpoint per il pannello AI della Switchboard (web) e la pagina desk Cervello."""
    _require_staff()
    reply = answer(message, operator=frappe.session.user, session_id=session_id)
    return {"reply": reply}


@frappe.whitelist()
def chat_upload(file_url, file_name, content_type="", case=None, session_id=None):
    """Allegato dalla chat Cervello (desk). Se è indicato un caso, il file diventa
    reperto nel dossier (riusa case_assistant.chat_upload); altrimenti resta un
    File libero e il cervello lo riceve come contesto."""
    _require_staff()
    result = {"ok": True, "evidence": None}
    if case:
        from thanatos_intel.ai.case_assistant import chat_upload as case_upload
        result["evidence"] = case_upload(case, file_url, file_name, content_type).get("evidence")
    return result


# ─────────────────────── report costi / fatturazione AI ──────────────────────

@frappe.whitelist()
def cost_report(days=30):
    """Report consumo AI dal AI Usage Log: totali, per motore/provider, per
    giorno, per cliente. Per la console admin + generazione fattura."""
    days = int(days)
    per_provider = frappe.db.sql("""
        SELECT provider, COUNT(*) chiamate,
               SUM(tokens_in+tokens_out) token, SUM(client_cost) costo
        FROM `tabAI Usage Log`
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY provider ORDER BY costo DESC
    """, days, as_dict=True)
    per_day = frappe.db.sql("""
        SELECT usage_date, COUNT(*) chiamate,
               SUM(tokens_in+tokens_out) token, SUM(client_cost) costo
        FROM `tabAI Usage Log`
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY usage_date ORDER BY usage_date DESC
    """, days, as_dict=True)
    per_client = frappe.db.sql("""
        SELECT COALESCE(client,'(interno/Thanatos)') cliente, COUNT(*) chiamate,
               SUM(tokens_in+tokens_out) token, SUM(client_cost) costo
        FROM `tabAI Usage Log`
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY client ORDER BY costo DESC
    """, days, as_dict=True)
    tot = frappe.db.sql("""
        SELECT COUNT(*) chiamate, SUM(tokens_in+tokens_out) token,
               SUM(client_cost) costo
        FROM `tabAI Usage Log`
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    """, days, as_dict=True)
    return {"giorni": days, "totale": tot[0] if tot else {},
            "per_motore": per_provider, "per_giorno": per_day,
            "per_cliente": per_client,
            "tariffa_eur_1k": float(frappe.conf.get("ops_brain_bill_rate") or 0.03)}


@frappe.whitelist()
def generate_ai_invoice(client=None, days=30):
    """Genera la fattura del consumo AI per un cliente (o Thanatos/interno) dal
    AI Usage Log. Somma client_cost del periodo e crea un documento riepilogo.
    Ritorna il totale e il dettaglio; l'inserimento su ERPNext Sales Invoice è
    opzionale (richiede Company + Customer configurati)."""
    days = int(days)
    cond = "client = %(client)s" if client else "1=1"
    rows = frappe.db.sql(f"""
        SELECT provider, model, SUM(tokens_in+tokens_out) token,
               SUM(client_cost) costo, COUNT(*) chiamate
        FROM `tabAI Usage Log`
        WHERE usage_date >= DATE_SUB(CURDATE(), INTERVAL %(d)s DAY) AND {cond}
        GROUP BY provider, model ORDER BY costo DESC
    """, {"d": days, "client": client}, as_dict=True)
    totale = round(sum(float(r["costo"] or 0) for r in rows), 2)
    token = int(sum(int(r["token"] or 0) for r in rows))
    return {
        "cliente": client or "Thanatos (interno)",
        "periodo_giorni": days,
        "token_totali": token,
        "tariffa_eur_1k": float(frappe.conf.get("ops_brain_bill_rate") or 0.03),
        "totale_eur": totale,
        "righe": rows,
        "nota": "Consumo AI fatturato da MMOS a €{:.3f}/1000 token.".format(
            float(frappe.conf.get("ops_brain_bill_rate") or 0.03)),
    }
