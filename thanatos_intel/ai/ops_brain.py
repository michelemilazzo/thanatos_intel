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


# ─────────────────────── autorizzazione / scope utente ───────────────────────

def _scope(user=None):
    """Scope casi dell'utente: None = full access (operatore/admin), altrimenti
    set dei soli casi che l'utente (cliente) può vedere."""
    from thanatos_intel.permissions import is_full_access, visible_case_names
    user = user or frappe.session.user
    if is_full_access(user):
        return None
    return set(visible_case_names(user) or [])


def _in_scope(case):
    """True se il caso è visibile all'utente corrente (o se full access)."""
    sc = getattr(frappe.local, "_ob_scope", None)
    return sc is None or (case in sc)


def _is_client():
    """True se l'utente corrente è un cliente (scope ristretto), non operatore."""
    return getattr(frappe.local, "_ob_scope", None) is not None


def _lead_case(lead):
    return frappe.db.get_value("Intel Lead", lead, "linked_case")


def _file_allowed(file_url):
    """True se il file appartiene a un caso/lead nello scope dell'utente."""
    sc = getattr(frappe.local, "_ob_scope", None)
    if sc is None:
        return True
    f = frappe.db.get_value("File", {"file_url": file_url},
                            ["attached_to_doctype", "attached_to_name"], as_dict=True)
    if not f:
        return False
    dt, dn = f.attached_to_doctype, f.attached_to_name
    if dt == "Investigation Case":
        return dn in sc
    if dt == "Intel Lead":
        lc = _lead_case(dn)
        return bool(lc and lc in sc)
    if dt == "Investigation Evidence":
        c = frappe.db.get_value("Investigation Evidence", dn, "investigation_case")
        return bool(c and c in sc)
    return False


_DENIED = {"error": "Accesso negato: non sei autorizzato per questo caso/documento."}
_DENIED_OSINT = {"error": "Strumento riservato agli operatori Thanatos."}


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
    sc = getattr(frappe.local, "_ob_scope", None)
    out = {}
    for k, v in r.items():
        if not v:
            continue
        if sc is not None:
            # cliente: filtra ai soli casi visibili
            if k == "cases":
                v = [x for x in v if x.get("name") in sc]
            elif k == "evidences":
                v = [x for x in v if x.get("investigation_case") in sc]
            elif k in ("chats", "messages"):
                v = [x for x in v if _lead_case(x.get("lead") or x.get("name")) in sc]
            elif k == "clients":
                v = []  # anagrafiche clienti non esposte ai clienti
        if v:
            out[k] = v
    return out or {"info": "nessun risultato"}


def _t_list_cases(status=None, **kw):
    filters = {}
    if status:
        filters["status"] = status
    sc = getattr(frappe.local, "_ob_scope", None)
    if sc is not None:
        filters["name"] = ["in", list(sc) or ["__none__"]]
    return frappe.get_all("Investigation Case", filters=filters,
                          fields=["name", "case_title", "status", "case_type",
                                  "priority", "client"],
                          order_by="modified desc", limit=15)


def _t_case_detail(case=None, **kw):
    if not case:
        return {"error": "manca il codice caso"}
    if not _in_scope(case):
        return dict(_DENIED)
    from thanatos_intel.api.centralino import get_case_detail
    try:
        return get_case_detail(case)
    except Exception as e:
        return {"error": str(e)}


def _t_stats(**kw):
    if _is_client():
        return {"error": "Statistiche riservate agli operatori."}
    return {"snapshot": _structure_snapshot()}


def _t_screening_kyc(nome=None, mode="pep", case=None, **kw):
    if _is_client():
        return dict(_DENIED_OSINT)
    if not nome:
        return {"error": "manca il nominativo"}
    from thanatos_intel.osint.openapi_client import screening_kyc
    return screening_kyc(nome, mode=mode, investigation_case=case)


def _t_soci_ubo(piva=None, case=None, **kw):
    if _is_client():
        return dict(_DENIED_OSINT)
    if not piva:
        return {"error": "manca la P.IVA"}
    from thanatos_intel.osint.openapi_client import soci_titolari
    return soci_titolari(piva, investigation_case=case)


def _t_negativita(id=None, case=None, **kw):
    if _is_client():
        return dict(_DENIED_OSINT)
    if not id:
        return {"error": "manca CF o P.IVA"}
    from thanatos_intel.osint.openapi_client import negativita
    return negativita(id, investigation_case=case)


def _t_visura(piva=None, case=None, **kw):
    if _is_client():
        return dict(_DENIED_OSINT)
    if not piva:
        return {"error": "manca la P.IVA"}
    from thanatos_intel.osint.openapi_client import visura
    return visura(piva, investigation_case=case)


def _t_case_tool(case=None, instruction=None, **kw):
    """Delega all'assistente del caso (esegue lo strumento reale: cluster,
    dossier, proforma, avanzamento, collegamenti, assicurazione…)."""
    if not case or not instruction:
        return {"error": "servono case e instruction"}
    if not _in_scope(case):
        return dict(_DENIED)
    if _is_client():
        return dict(_DENIED_OSINT)  # strumenti operativi solo agli operatori
    from thanatos_intel.ai.case_assistant import case_ai_chat
    return case_ai_chat(case, instruction)


def _t_list_documents(case=None, lead=None, **kw):
    """Elenca TUTTI i file allegati a un caso o lead (anche quelli non ancora
    ingeriti come reperti), con stato. Serve al cervello per vedere i documenti
    che l'operatore ha appena mandato, prima che siano processati."""
    docs = []
    if case and not _in_scope(case):
        return dict(_DENIED)
    if lead and _is_client():
        lc = _lead_case(lead)
        if not (lc and _in_scope(lc)):
            return dict(_DENIED)
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
    # senza case/lead → allegati WhatsApp recenti su TUTTA la struttura (solo operatori)
    if not case and not lead:
        if _is_client():
            return dict(_DENIED)
        rows = frappe.db.sql("""
            SELECT f.file_name, f.file_url, f.creation, f.attached_to_name AS lead,
                   l.source_name, l.source_identifier, l.linked_case
            FROM `tabFile` f
            JOIN `tabIntel Lead` l ON l.name = f.attached_to_name
            WHERE f.attached_to_doctype = 'Intel Lead'
            ORDER BY f.creation DESC LIMIT 30
        """, as_dict=True)
        for r in rows:
            docs.append({
                "file": r.file_name, "url": r.file_url,
                "da": r.source_name or r.source_identifier,
                "chat": r.lead, "caso": r.linked_case or "—",
                "quando": str(r.creation)[:16], "stato": "allegato WhatsApp",
            })
        return {"count": len(docs), "documents": docs,
                "nota": "Ultimi 30 allegati WhatsApp su tutte le chat. Per leggerne uno usa read_document(file_url)."}
    return {"count": len(docs), "documents": docs}


def _t_read_passport(file_url=None, vision=True, **kw):
    """Legge un documento d'identità (passaporto/CIE) via lettore MRZ ICAO 9303:
    estrae nome, numero documento, nazionalità, scadenza, valida i check-digit e
    dà un verdetto di autenticità. Read-only (non crea Passport Analysis)."""
    if not file_url:
        return {"error": "manca file_url"}
    if not _file_allowed(file_url):
        return dict(_DENIED)
    import os
    from thanatos_intel.thanatos_documents.passport import analyzer
    path = frappe.get_site_path("private", "files",
                                file_url.split("/private/files/")[-1])
    if not os.path.exists(path):
        path = frappe.get_site_path("public", "files", file_url.split("/files/")[-1])
    if not os.path.exists(path):
        return {"error": "file non trovato"}
    try:
        r = analyzer.analyze(path)
    except Exception as e:
        return {"error": str(e)[:200]}
    # MRZ letta e validata → dato verificato (check-digit ICAO)
    if r.get("mrz_line_1"):
        return {
            "is_document": True, "fonte": "MRZ (verificata)",
            "tipo": r.get("document_type"), "cognome": r.get("surname"),
            "nome": r.get("given_names"), "numero": r.get("document_number"),
            "nazionalita": r.get("nationality"), "stato_emittente": r.get("issuing_country"),
            "nascita": str(r.get("dob") or ""), "scadenza": str(r.get("expiry") or ""),
            "sesso": r.get("sex"), "mrz_valido": r.get("mrz_valid"),
            "verdetto": r.get("verdict"), "risk_score": r.get("risk_score"),
            "anomalie": r.get("anomalies"),
        }
    # MRZ non leggibile → lettura-visione. OpenRouter free (veloce, gratis);
    # Claude CLI solo se richiesto esplicitamente (claude_fallback=True): è ~90s
    # e da solo rischia il timeout web, quindi off di default nel percorso chat.
    if not vision:
        return {"is_document": False, "nota": "MRZ non leggibile (foto scarsa)"}
    v = _openrouter_vision_id(path)
    fonte = "lettura AI (OpenRouter free)"
    if not v and kw.get("claude_fallback"):
        v = _claude_vision_id(path)
        fonte = "lettura AI (Claude)"
    if v:
        v["is_document"] = True
        v["fonte"] = f"{fonte} — DA CONFERMARE sull'originale"
        return v
    return {"is_document": False,
            "nota": "modelli visione occupati (free tier): riprova tra poco, "
                    "oppure carica uno scan più nitido per la lettura MRZ verificata"}


# modelli visione free su OpenRouter, in ordine di preferenza (fallback su 429)
_OR_VISION_MODELS = ("nvidia/nemotron-nano-12b-v2-vl:free",
                     "google/gemma-4-26b-a4b-it:free")


def _url_to_path(file_url):
    """Risolve un file_url Frappe al path locale (private/public). None se assente."""
    import os
    if not file_url:
        return None
    p = frappe.get_site_path("private", "files", file_url.split("/private/files/")[-1])
    if not os.path.exists(p):
        p = frappe.get_site_path("public", "files", file_url.split("/files/")[-1])
    return p if os.path.exists(p) else None


def _openrouter_vision_id(path, quick=False):
    """Legge un documento d'identità con un modello-visione FREE su OpenRouter.
    NON verificato dai check-digit → sempre da confermare. None se manca la chiave
    o tutti i modelli falliscono/rate-limitano. quick=True: 1 modello, 15s (per il
    batch, evita di sommare latenze e sforare il timeout web)."""
    import base64
    import json as _json
    import re as _re
    import urllib.request
    key = _vault("openrouter_key") or frappe.conf.get("openrouter_api_key")
    if not key:
        return None
    url = (_vault("openrouter_url") or "https://openrouter.ai/api/v1").rstrip("/")
    try:
        b64 = base64.b64encode(open(path, "rb").read()).decode()
    except Exception:
        return None
    prompt = ("Documento d'identità. Estrai SOLO un JSON con: tipo, cognome, nome, "
              "numero, nazionalita, nascita, scadenza, sesso. null se illeggibile. "
              "Nessun altro testo.")
    content = [{"type": "text", "text": prompt},
               {"type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
    models = _OR_VISION_MODELS[:1] if quick else _OR_VISION_MODELS
    to = 15 if quick else 22
    for model in models:
        body = _json.dumps({"model": model, "temperature": 0,
                            "messages": [{"role": "user", "content": content}]}).encode()
        req = urllib.request.Request(f"{url}/chat/completions", data=body, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = _json.loads(urllib.request.urlopen(req, timeout=to).read())
            txt = r["choices"][0]["message"]["content"]
            u = r.get("usage") or {}
            _track("openrouter", model, int(u.get("prompt_tokens", 0)),
                   int(u.get("completion_tokens", 0)))
            m = _re.search(r"\{.*\}", txt, _re.DOTALL)
            if not m:
                continue
            f = _json.loads(m.group(0))
            return {k: f.get(k) for k in ("tipo", "cognome", "nome", "numero",
                    "nazionalita", "nascita", "scadenza", "sesso")}
        except Exception:
            continue  # 429/timeout/parse → prova il modello successivo
    return None


def _claude_vision_id(path):
    """Legge un documento d'identità con Claude CLI (multimodale) quando l'MRZ
    ottica non è leggibile. NON verificato dai check-digit → sempre da confermare.
    Ritorna dict campi o None se il CLI non è disponibile/fallisce."""
    import json as _json
    import os
    import subprocess
    claude = frappe.conf.get("ops_brain_claude_bin") or "/usr/local/bin/claude"
    if not os.path.exists(claude):
        return None
    prompt = (f"Leggi il documento d'identità nell'immagine {path}. Estrai SOLO un JSON "
              "con: tipo, cognome, nome, numero, nazionalita, nascita, scadenza, sesso. "
              "Se un campo non è leggibile con certezza mettilo a null. Nessun altro testo.")
    env = dict(os.environ)
    env["HOME"] = frappe.conf.get("ops_brain_home") or "/home/frappe"
    try:
        r = subprocess.run([claude, "-p", prompt, "--allowedTools", "Read",
                            "--output-format", "json"],
                           capture_output=True, text=True, timeout=175, env=env)
        d = _json.loads((r.stdout or "").strip())
        if d.get("is_error"):
            return None
        u = d.get("usage") or {}
        _track("claude", "claude-vision",
               int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)),
               int(u.get("output_tokens", 0)))
        # estrai il JSON dal testo del risultato
        import re as _re
        txt = (d.get("result") or "").strip()
        m = _re.search(r"\{.*\}", txt, _re.DOTALL)
        if not m:
            return None
        fields = _json.loads(m.group(0))
        return {k: fields.get(k) for k in
                ("tipo", "cognome", "nome", "numero", "nazionalita", "nascita",
                 "scadenza", "sesso")}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ops_brain claude vision id")
        return None


def _t_read_document(file_url=None, **kw):
    """Legge/OCR il contenuto testuale COMPLETO di un documento on-demand (PDF,
    immagine, docx…). Usa questo per analizzare un allegato che non è ancora un
    reperto sintetizzato."""
    if not file_url:
        return {"error": "manca file_url"}
    if not _file_allowed(file_url):
        return dict(_DENIED)
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
    if not _in_scope(case) or _is_client():
        return dict(_DENIED)
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
    "read_passport": _t_read_passport,    # {file_url} → lettore MRZ passaporto/CIE
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
- list_documents {case?, lead?}: elenca i file allegati a un caso o lead. SENZA parametri elenca gli ultimi allegati WhatsApp su TUTTE le chat (usa questo se l'operatore chiede "gli allegati su whatsapp" senza citare un caso)
- read_document {file_url}: legge/OCR il testo completo di un documento on-demand (per analizzare un allegato non ancora sintetizzato)
- read_passport {file_url}: lettore documenti d'identità (passaporto/CIE) — MRZ ICAO 9303: nome, numero, nazionalità, scadenza, check-digit e verdetto autenticità. Usa questo per foto di documenti anziché read_document
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
    "- Quando citi un caso usa il codice CASE-AAAA-N.\n"
    "ANTI-INVENZIONE (regola ferrea): non affermare MAI che qualcosa e' «risolto», "
    "«fatto», «funziona», «inviato», «pronto» o simili se non l'hai verificato con "
    "uno strumento o non e' nei dati reali; in caso, dillo («non l'ho verificato», "
    "«non ho questo dato»). Non inventare URL, link, codici, numeri, date o stati. "
    "Non ricostruire a memoria i messaggi precedenti («te l'ho dato prima», «l'unico "
    "link era X»): NON hai una memoria affidabile della chat — se ti chiedono qualcosa "
    "di prima e non ce l'hai davanti, dillo e proponi di rigenerarlo con lo strumento "
    "giusto. Meglio «non lo so, verifico» che una risposta sicura ma falsa: in "
    "un'indagine un dato falso e' peggio di nessun dato. "
    "Rispondi prima e in modo diretto alla domanda esatta; tono umano e asciutto, mai "
    "robotico ne' con formule ripetute.\n"
)

# System prompt per i CLIENTI (scope ristretto ai propri casi).
_SYS_CLIENT = (
    "Sei l'assistente di Thanatos Intel per un CLIENTE. Dagli del Lei, tono "
    "cortese e professionale. Il cliente vede SOLO i propri casi: gli strumenti "
    "sono limitati ai suoi dati e alcuni sono riservati agli operatori (se uno "
    "strumento risponde 'Accesso negato' o 'riservato agli operatori', spiega "
    "gentilmente che quell'informazione la gestisce il team Thanatos).\n\n"
    "STRUMENTI (rispondi con JSON {\"tool\":\"nome\",\"args\":{...}} per usarne uno):\n"
    "- list_cases {}: elenca i TUOI casi\n"
    "- case_detail {case}: dettaglio di un tuo caso (stato, documenti, avanzamento)\n"
    "- global_search {q}: cerca nei tuoi casi/documenti\n"
    "- list_documents {case}: elenca i documenti di un tuo caso\n"
    "- read_document {file_url}: leggi un documento di un tuo caso\n"
    "\nREGOLE:\n"
    "- Se serve un dato, USA uno strumento: rispondi SOLO con il JSON.\n"
    "- Altrimenti rispondi in testo, cortese e chiaro (max ~140 parole).\n"
    "- Non promettere risultati, non dare consulenza legale, non rivelare dati "
    "di altri clienti o casi non tuoi.\n"
    "- Non inventare mai informazioni (stati, link, date, importi): se non ha il "
    "dato, usi uno strumento oppure dica che lo verifica il team Thanatos. Non "
    "ricostruisca a memoria cosa e' stato detto prima; se non ce l'ha davanti, lo "
    "dica con onesta'.\n"
    "- Rispondi PRIMA e in modo diretto alla domanda esatta del cliente; non cambiare "
    "argomento ne' rispondere a lato.\n"
    "- Tono UMANO e caldo, come una persona competente al telefono: frasi brevi e "
    "naturali, niente gergo burocratico ne' formule ripetute; empatia vera quando serve.\n"
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
    "mcp__thanatos__ingest_document", "mcp__thanatos__web_search",
]

_CLI_SYS = (
    "Sei il cervello operativo di Thanatos Intel, agenzia investigativa (sede "
    "Romania, GDPR/Legea 329-2003). Parli con un OPERATORE interno: dagli del tu, "
    "tono diretto e concreto, niente disclaimer. Hai gli strumenti MCP thanatos "
    "(stats, global_search, list_cases, case_detail, screening_kyc, soci_ubo, "
    "negativita, visura, case_tool, run_query): USALI per rispondere con dati "
    "reali invece di inventare. Per cercare su INTERNET (notizie, profili di "
    "persone, riscontri pubblici) usa lo strumento web_search (ricerca vera con "
    "fonti): NON dire mai che la ricerca web non e' autorizzata, hai web_search. "
    "Risposte brevi e operative, in italiano. Quando "
    "citi un caso usa il codice CASE-AAAA-N. Per le AZIONI reali (usare uno "
    "strumento) non chiedere conferme: agisci. Ma NON inventare: non affermare mai "
    "che qualcosa e' risolto/fatto/funziona/inviato se non l'hai verificato con uno "
    "strumento; non inventare URL, link, codici o stati; non ricostruire a memoria i "
    "messaggi precedenti (non hai una memoria affidabile della chat). Se non hai un "
    "dato, dillo e usa lo strumento giusto — meglio «verifico» che una risposta "
    "sicura ma falsa."
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
        out, usage = llm_fn(convo, _SYS_CLIENT if _is_client() else _SYS)
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


_TRIVIAL_RE = re.compile(
    r"^(ciao|salve|buongiorno|buonasera|buonanotte|grazie|ok(ay)?|perfetto|"
    r"va\s+bene|ottimo|si|s[i\u00ec]|no|esatto|capito|d'accordo|bene|prego|"
    r"ottimo\s+lavoro)[\s!.,\U0001F440-\U0001FAFF]*$", re.I)


def _needs_tools(text):
    """True se il messaggio e' una domanda fattuale/operativa (-> motore con
    strumenti). False solo per i messaggi banali (saluti/conferme) senza dati."""
    t = (text or "").strip()
    if not t or t.startswith("["):
        return False
    if _TRIVIAL_RE.match(t):
        return False
    return True


def answer(text, operator=None, lead_name=None, session_id=None, max_steps=3, user=None):
    """Cervello operativo con AUTORIZZAZIONE. `user` (o operator) determina lo
    scope: operatore/admin = tutti i casi e strumenti; cliente = SOLO i propri
    casi (visible_case_names), niente OSINT/stats/strumenti operativi.
    Motore via site_config `ops_brain_engine` (auto|cli|codex|ollama|openrouter|
    gateway). Ogni motore cade sul successivo."""
    # scope autorizzazione (thread-safe, letto da tutti i tool). L'operatore
    # WhatsApp arriva come NOME Investigator → risolvi al suo platform_user.
    scope_user = user
    if not scope_user and operator:
        pu = frappe.db.get_value("Investigator", operator, "platform_user")
        scope_user = pu or operator
    scope_user = scope_user or frappe.session.user
    frappe.local._ob_scope = _scope(scope_user)
    is_client = frappe.local._ob_scope is not None

    # caso di contesto (se la chat è agganciata o citato nel testo) — validato su scope
    ctx_case = None
    if lead_name:
        ctx_case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    m = re.search(r"CASE-\d{4}-\d+", text or "", re.I)
    if m and frappe.db.exists("Investigation Case", m.group(0).upper()):
        ctx_case = m.group(0).upper()
    if ctx_case and not _in_scope(ctx_case):
        ctx_case = None  # cliente non può agganciare un caso non suo

    tl = (text or "").lower()

    # shortcut lettura AI on-demand di un singolo documento citato per nome file
    fm = re.search(r"(wa-[\w.-]+\.(?:jpg|jpeg|png|webp|pdf|tif|tiff))", tl)
    if not is_client and fm and re.search(r"legg|analizz|estrai|documento|passaport|identit", tl):
        fn = fm.group(1)
        furl = frappe.db.get_value("File", {"file_name": ["like", fn]}, "file_url") \
            or frappe.db.get_value("File", {"file_url": ["like", f"%{fn}"]}, "file_url")
        if not furl:
            return f"Non trovo l'allegato {fn}."
        pp = _t_read_passport(file_url=furl, vision=True)
        if pp.get("is_document"):
            testa = (f"{pp.get('tipo') or 'documento'} · {pp.get('cognome') or ''} "
                     f"{pp.get('nome') or ''} · n. {pp.get('numero') or '?'} · "
                     f"{pp.get('nazionalita') or '?'} · scad. {pp.get('scadenza') or '?'}"
                     + (f" · sesso {pp.get('sesso')}" if pp.get('sesso') else ""))
            if pp.get("mrz_valido") is not None:
                return (f"🛂 **{fn}** ({pp.get('fonte')}):\n{testa}\n"
                        f"MRZ {'valida ✅' if pp.get('mrz_valido') else 'NON valida ⚠️'} · "
                        f"verdetto {pp.get('verdetto')}"
                        + (f"\n⚠️ {pp.get('anomalie')}" if pp.get('anomalie') else ""))
            return f"🛂 **{fn}**:\n{testa}\n📷 {pp.get('fonte')}"
        r = _t_read_document(file_url=furl) or {}
        return f"📄 **{fn}**:\n{(r.get('text') or '(illeggibile)')[:1500]}"

    # shortcut deterministico: "allegati/documenti whatsapp" senza caso citato →
    # esegue list_documents (+ OCR se richiesto) coi dati reali. Il modello
    # economico a volte allucina invece di invocare il tool: qui bypassiamo.
    if (not is_client and not ctx_case
            and re.search(r"allegat|document|file", tl)
            and re.search(r"whatsapp|\bwa\b|chat", tl)
            and re.search(r"elenc|lista|mostra|vedi|guarda|quali|tutti|legg|analizz|contenut|contengon|apri", tl)):
        data = _t_list_documents()
        docs = data.get("documents") or []
        if not docs:
            return "Nessun allegato WhatsApp trovato nelle chat."
        want_read = bool(re.search(r"legg|analizz|contenut|contengon|apri|cosa c", tl))
        if want_read:
            lines = [f"📎 Leggo gli ultimi allegati WhatsApp:"]
            for d in docs[:8]:
                url = d.get("url")
                is_img = str(d.get("file") or "").lower().endswith(
                    (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".pdf"))
                # 1) MRZ ottica (veloce, verificata)
                pp = _t_read_passport(file_url=url, vision=False) if is_img else {}
                if pp.get("is_document"):
                    ver = pp.get("verdetto") or "?"
                    lines.append(
                        f"\n• **{d.get('file')}** (caso {d.get('caso')}) — 🛂 DOCUMENTO ({pp.get('fonte')}):\n"
                        f"  {pp.get('tipo') or 'documento'} · {pp.get('cognome') or ''} {pp.get('nome') or ''} · "
                        f"n. {pp.get('numero') or '?'} · {pp.get('nazionalita') or '?'} · "
                        f"scad. {pp.get('scadenza') or '?'}\n"
                        f"  MRZ {'valida ✅' if pp.get('mrz_valido') else 'NON valida ⚠️'} · "
                        f"verdetto **{ver}** (risk {pp.get('risk_score')})"
                        + (f"\n  ⚠️ {pp.get('anomalie')}" if pp.get('anomalie') else ""))
                    continue
                r = _t_read_document(file_url=url) or {}
                txt = (r.get("text") or "").strip()
                looks_id = is_img and any(k in txt.upper() for k in
                                          ("PASSPORT", "PASSAPORTO", "REPUBBLICA", "CARTA D",
                                           "IDENTITY", "IDENTITA", "MRZ", "<<"))
                # documento scadente → lettura-visione on-demand (OpenRouter ~5s per file):
                # in blocco N letture sincrone sforerebbero il timeout web.
                if looks_id:
                    lines.append(
                        f"\n• **{d.get('file')}** (caso {d.get('caso')}) — 🛂 documento d'identità "
                        f"(foto scarsa). Dimmi «leggi il documento {d.get('file')}» per l'estrazione AI (~5s).")
                    continue
                snippet = (txt[:400] + "…") if len(txt) > 400 else (txt or "(vuoto/illeggibile)")
                lines.append(f"\n• **{d.get('file')}** — da {d.get('da')} "
                             f"(caso {d.get('caso')}, {d.get('quando')}):\n{snippet}")
            if len(docs) > 8:
                lines.append(f"\n(+{len(docs) - 8} altri allegati non letti — chiedi «leggi i prossimi» o cita un caso)")
            return "\n".join(lines)
        lines = [f"📎 Ultimi {len(docs)} allegati WhatsApp:"]
        for d in docs[:30]:
            lines.append(f"• {d.get('file')} — da {d.get('da')} "
                         f"(chat {d.get('chat')}, caso {d.get('caso')}, {d.get('quando')})")
        lines.append("\nDimmi «leggi gli allegati whatsapp» per l'OCR o «ingerisci sul caso CASE-… » per farne reperti.")
        return "\n".join(lines)

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

    # CLIENTE: MAI i motori CLI (Claude/Codex girano come Administrator via MCP =
    # bypasserebbero lo scope). Solo motori in-process con i tool scoped.
    if is_client:
        r = _chain(E_cheap, E_gw, E_ollama)
    # OPERATORE: router a costi scalati completo.
    elif engine == "auto":
        # Domande fattuali/operative -> motore con STRUMENTI (Claude) per primo,
        # cosi risponde coi dati reali e non inventa. Solo i messaggi banali
        # (saluti/conferme) restano sull'economico per risparmiare.
        if _needs_tools(text):
            r = _chain(E_claude, E_codex, E_cheap, E_gw, E_ollama)
        else:
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


@frappe.whitelist()
def ask(message, session_id=None):
    """Endpoint AI: operatori (PWA Switchboard) e clienti (portale). Lo scope è
    calcolato dall'utente loggato: operatore = tutto, cliente = solo i suoi casi."""
    if frappe.session.user == "Guest":
        frappe.throw("Login richiesto")
    reply = answer(message, user=frappe.session.user, session_id=session_id)
    return {"reply": reply}


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
