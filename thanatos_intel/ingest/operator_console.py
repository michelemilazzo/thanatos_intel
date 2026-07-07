"""Canale operatore su WhatsApp.

Quando il mittente di un messaggio WhatsApp e' un investigatore noto (numero che
matcha Investigator.phone), il messaggio NON e' di un cliente: e' un comando
operativo. L'operatore puo' inviare documenti e poi un comando testuale
("elabora gli allegati ed apri un caso") per far creare a MMOS AI un
Investigation Case con i documenti gia' ingeriti (OCR + estrazione + reperti).
"""
import re
import frappe
from frappe.utils import now_datetime, get_url


def _digits(n):
    return re.sub(r"\D", "", n or "")


def _operator_user(operator):
    """Risolve l'Investigator nel suo User (campo platform_user). Fallback Administrator.
    Serve per i campi Link→User (promoted_by, notifiche), che NON accettano il nome
    dell'Investigator."""
    u = frappe.db.get_value("Investigator", operator, "platform_user") if operator else None
    return u or "Administrator"


def find_operator(number):
    """Ritorna il nome dell'Investigator se il numero corrisponde a un operatore."""
    d = _digits(number)
    if len(d) < 8:
        return None
    tail = d[-9:]
    for r in frappe.get_all("Investigator", fields=["name", "phone"], limit=0):
        if r.phone and _digits(r.phone).endswith(tail):
            return r.name
    return None


_OPEN_CASE_RE = re.compile(
    r"(apr[ai].{0,12}\bcas[oi]\b|crea.{0,12}\bcas[oi]\b|elabor.{0,20}allegat|"
    r"\bapri\b.{0,12}\bpratica\b|processa.{0,20}allegat|analizz.{0,20}allegat)",
    re.I,
)
_HELP_RE = re.compile(r"\b(aiuto|help|comandi|cosa puoi fare)\b", re.I)
_REPROCESS_RE = re.compile(
    r"(rilegg|ri-?legg|ri-?process|riprov.{0,12}ocr|ri-?fai.{0,10}ocr|"
    r"\bleggi\b.{0,14}(allegat|document)|ocr.{0,14}divers)", re.I)
_QUESTIONS_RE = re.compile(
    r"(domand.{0,14}(document|allegat|reperti|cas)|fai.{0,8}le domand|"
    r"poni.{0,14}domand|investigatore digitale|domande investigative)", re.I)
_PROFORMA_RE = re.compile(
    r"\b(proforma|pro\s*forma|preventivo|quotazione)\b", re.I)
_PAYMENT_RE = re.compile(
    r"\b(link\s*(di\s*)?pagamento|pagamento|paga(re)?|incassa|"
    r"checkout|stripe\s*link)\b", re.I)
_DELIVER_RE = re.compile(
    r"(manda.{0,12}(al\s*)?cliente|invia.{0,12}(al\s*)?cliente|"
    r"consegna.{0,12}(al\s*)?cliente|spedisci.{0,12}cliente|"
    r"trasmett.{0,12}cliente|recapita.{0,12}cliente)", re.I)
_STATUS_RE = re.compile(
    r"\b(stato|status|sintesi|riassumi|riassunto|brief|situazione)\b", re.I)
_DOCS_RE = re.compile(
    r"^\s*(documenti|elenco\s+document|lista\s+document|files?|allegati)\s*$",
    re.I)
_CLOSE_RE = re.compile(
    r"^\s*(chiudi(\s+il)?\s+cas[oi]|archivia(\s+il)?\s+cas[oi]|chiudi\s+pratica)\b",
    re.I)
_ASSIGN_RE = re.compile(
    r"\bassegna(re)?\s+(a|al|alla)\s+([\w\.\-]+(\s+(?!CASE-)[\w\.\-]+)*)\b", re.I)
_ADD_TO_CASE_RE = re.compile(
    # match bidirezionale: "verbo … caso" oppure "caso … verbo".
    # Radici verbali per coprire coniugazioni (metterli, aggiungerli, allegali, ecc.)
    r"("
    r"\b(mett|aggiung|attacc|alleg|inseris|caric).{0,50}\b(al\s+)?(cas[oi]|pratica|CASE-\d{4}-\d+)\b"
    r"|"
    r"\b(al\s+)?(cas[oi]|pratica|CASE-\d{4}-\d+)\b.{0,50}\b(mett|aggiung|attacc|alleg|inseris|caric)"
    r")", re.I)


# ─── Ruoli operatore ─────────────────────────────────────────────────────────

# Ruolo derivato dai role del platform_user collegato all'Investigator:
#  - super_admin  → System Manager (modifiche tecniche, comandi distruttivi)
#  - admin        → Investigation Manager (gestione casi, assegnazioni, chiusure)
#  - investigator → Investigator (operativo: aperture, OCR, proforma, pagamenti)
_ROLE_RANK = {"super_admin": 3, "admin": 2, "investigator": 1, "guest": 0}


def _operator_role(operator):
    """Ritorna il ruolo dell'operatore: super_admin | admin | investigator | guest."""
    if not operator:
        return "guest"
    user = _operator_user(operator)
    roles = set(frappe.get_roles(user) or [])
    if "System Manager" in roles:
        return "super_admin"
    if "Investigation Manager" in roles:
        return "admin"
    if "Investigator" in roles:
        return "investigator"
    return "guest"


def _can(operator, min_role):
    return _ROLE_RANK.get(_operator_role(operator), 0) >= _ROLE_RANK.get(min_role, 99)


# ─── Comunicazione col cliente del caso ──────────────────────────────────────

def _client_lead_phone(case):
    """Ritorna (wa_phone_thanatos, client_wa_number, client_lead_name) per il caso.
    Cerca il Intel Lead promosso col caso; se manca, ritorna (None, None, None)."""
    lead = frappe.db.get_value("Intel Lead", {"linked_case": case},
                               ["name", "source_identifier", "whatsapp_number"],
                               as_dict=True, order_by="creation desc")
    if not lead:
        return None, None, None
    return lead.whatsapp_number, lead.source_identifier, lead.name


def _send_to_client(case, body):
    """Invia un messaggio testuale al cliente del caso (via WhatsApp).
    Ritorna True se riuscito, False se non c'è canale WA col cliente."""
    wa_phone, client_num, client_lead = _client_lead_phone(case)
    if not (wa_phone and client_num and client_lead):
        return False
    from thanatos_intel.ingest.wa_bot import _wa_doc, send_text
    wd = _wa_doc(wa_phone)
    if not wd:
        return False
    return send_text(wd, client_num, body, client_lead)


def _send_doc_to_client(case, content, filename, caption):
    wa_phone, client_num, client_lead = _client_lead_phone(case)
    if not (wa_phone and client_num and client_lead):
        return False
    return send_document_wa(wa_phone, client_num, content, filename, caption, client_lead)


def handle_operator_message(lead_name, wa_phone, sender, text, operator):
    """Instrada il messaggio dell'operatore. Solo i comandi riconosciuti agiscono;
    i messaggi normali/allegati vengono solo registrati (no bot, no auto-reply)."""
    t = (text or "").strip()
    if not t or t.startswith("["):
        return  # media/placeholder: gia' allegato, niente da fare
    if _OPEN_CASE_RE.search(t):
        frappe.enqueue(
            "thanatos_intel.ingest.operator_console.run_open_case",
            queue="long", timeout=1200,
            lead_name=lead_name, wa_phone=wa_phone, sender=sender, operator=operator,
        )
        _reply(wa_phone, sender, lead_name,
               "\U0001F6E0️ Ricevuto. Sto elaborando gli allegati e apro la "
               "pratica: le mando l'esito tra poco.")
        return
    # "aggiungi al caso CASE-XXX" — ingerisce gli allegati recenti come reperti del case
    if _ADD_TO_CASE_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Cita il caso (es. «aggiungi al caso CASE-2026-0026»).")
            return
        frappe.enqueue(
            "thanatos_intel.ingest.operator_console.run_add_docs_to_case",
            queue="long", timeout=1200,
            lead_name=lead_name, case=case, wa_phone=wa_phone,
            sender=sender, operator=operator,
        )
        _reply(wa_phone, sender, lead_name,
               f"\U0001F4CE Aggiungo gli allegati recenti al caso *{case}*. "
               "Ti confermo con l'esito.")
        return
    if _REPROCESS_RE.search(t):
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' ancora un caso collegato a questa chat. Prima «apri un caso».")
            return
        frappe.enqueue("thanatos_intel.ingest.operator_console.reprocess_case_docs",
                       queue="long", timeout=1800, case=case, lead_name=lead_name,
                       wa_phone=wa_phone, sender=sender)
        _reply(wa_phone, sender, lead_name,
               "\U0001F501 Rileggo i documenti del caso con l'OCR, le mando l'esito tra poco.")
        return
    if _QUESTIONS_RE.search(t):
        case = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' ancora un caso collegato a questa chat. Prima «apri un caso».")
            return
        frappe.enqueue("thanatos_intel.ai.doc_questions.generate_questions",
                       queue="long", timeout=1200, case=case, lead_name=lead_name,
                       wa_phone=wa_phone, sender=sender, post=1)
        _reply(wa_phone, sender, lead_name,
               "\U0001F575️ Da investigatore digitale: preparo le domande per ogni "
               "documento, gliele mando tra poco.")
        return
    if _PROFORMA_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' un caso collegato. Cita il caso (es. «proforma CASE-2026-0026») "
                   "o apri prima la pratica.")
            return
        frappe.enqueue("thanatos_intel.ingest.operator_console.run_send_proforma",
                       queue="long", timeout=600,
                       case=case, lead_name=lead_name, wa_phone=wa_phone,
                       sender=sender, operator=operator,
                       hours_senior=_int_in(t, "senior", 40),
                       hours_analyst=_int_in(t, "analyst", 30),
                       sconto=_int_in(t, "sconto", 0),
                       send_to_client=int(bool(_DELIVER_RE.search(t))))
        _reply(wa_phone, sender, lead_name,
               "\U0001F4C4 Genero la proforma per *" + case + "*"
               + (" e la mando al cliente." if _DELIVER_RE.search(t)
                  else " — te la inoltro a te per revisione."))
        return
    if _PAYMENT_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' un caso collegato. Cita il caso (es. «pagamento CASE-2026-0026»).")
            return
        frappe.enqueue("thanatos_intel.ingest.operator_console.run_send_payment_link",
                       queue="short", timeout=180,
                       case=case, lead_name=lead_name, wa_phone=wa_phone,
                       sender=sender, operator=operator)
        _reply(wa_phone, sender, lead_name,
               "\U0001F4B3 Preparo il link di pagamento e lo mando al cliente del caso *"
               + case + "*.")
        return
    if _DELIVER_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' un caso collegato. Cita il caso (es. «manda al cliente CASE-2026-0026»).")
            return
        frappe.enqueue("thanatos_intel.ingest.operator_console.run_deliver_to_client",
                       queue="long", timeout=900,
                       case=case, sender=sender, wa_phone=wa_phone, lead_name=lead_name,
                       operator=operator)
        _reply(wa_phone, sender, lead_name,
               "\U0001F4E4 Consegno relazione e documenti chiave al cliente del caso *"
               + case + "*. Ti confermo a fine invio.")
        return
    if _DOCS_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Non c'e' un caso collegato a questa chat.")
            return
        _reply(wa_phone, sender, lead_name, _docs_list(case))
        return
    if _STATUS_RE.search(t):
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name,
                   "Cita il caso (es. «stato CASE-2026-0026»).")
            return
        _reply(wa_phone, sender, lead_name, _case_brief(case))
        return
    if _CLOSE_RE.search(t):
        if not _can(operator, "admin"):
            _reply(wa_phone, sender, lead_name,
                   "⛔ Non hai i permessi per chiudere casi. Serve ruolo admin.")
            return
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name, "Cita il caso da chiudere.")
            return
        frappe.db.set_value("Investigation Case", case, "status", "Closed")
        frappe.db.commit()
        _reply(wa_phone, sender, lead_name,
               f"✅ Caso *{case}* chiuso.")
        return
    am = _ASSIGN_RE.search(t)
    if am:
        if not _can(operator, "admin"):
            _reply(wa_phone, sender, lead_name,
                   "⛔ Non hai i permessi per riassegnare. Serve ruolo admin.")
            return
        target = am.group(3)
        case = _resolve_case(lead_name, t)
        if not case:
            _reply(wa_phone, sender, lead_name, "Cita il caso da riassegnare.")
            return
        inv = frappe.db.get_value("Investigator",
                                  {"full_name": ["like", f"%{target}%"]}, "name")
        if not inv:
            _reply(wa_phone, sender, lead_name,
                   f"Non trovo un investigatore «{target}».")
            return
        frappe.db.set_value("Investigation Case", case, "assigned_to", inv)
        frappe.db.commit()
        _reply(wa_phone, sender, lead_name,
               f"✅ Caso *{case}* riassegnato a {inv}.")
        return
    if _HELP_RE.search(t):
        _reply(wa_phone, sender, lead_name, _help_text(operator))
        return
    # messaggio operatore libero → assistente AI operativo (co-pilota), in background
    frappe.enqueue(
        "thanatos_intel.ingest.operator_console.operator_assistant_reply",
        queue="short", timeout=200,
        lead_name=lead_name, wa_phone=wa_phone, sender=sender, text=t, operator=operator,
    )
    return


_OP_SYS = (
    "Sei l'assistente operativo interno di Thanatos Intel (agenzia investigativa, sede "
    "Romania, GDPR/Legea 329-2003). Parli su WhatsApp con un OPERATORE interno "
    "(investigatore/manager), NON con un cliente: dagli del tu, tono diretto e concreto, "
    "niente disclaimer commerciali ne' presentazioni dell'agenzia. Aiutalo nel lavoro: "
    "rispondi su casi/lead, riassumi documenti e pratiche, suggerisci i prossimi passi "
    "investigativi, redigi note/testi. Usa SOLO le informazioni nel contesto fornito; se "
    "un dato non c'e', dillo e indica come ottenerlo. Ricorda all'operatore, quando "
    "pertinente, che inviando documenti e scrivendo «elabora gli allegati ed apri un caso» "
    "apri una pratica con i reperti analizzati. Risposte brevi e operative (max ~120 "
    "parole), in italiano."
)


def _case_brief(case):
    c = frappe.db.get_value("Investigation Case", case,
                            ["case_title", "case_type", "status", "summary"],
                            as_dict=True) or {}
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["evidence_name", "notes"], limit=20)
    lines = [f"Caso {case}: {c.get('case_title')} [{c.get('status')}] "
             f"tipo {c.get('case_type')}"]
    if c.get("summary"):
        lines.append("Sintesi: " + c["summary"])
    if evs:
        lines.append(f"Reperti ({len(evs)}):")
        for e in evs[:12]:
            note = (e.notes or "").replace("\n", " ").strip()
            lines.append(f"  • {e.evidence_name}: {note[:140]}")
    return "\n".join(lines)


def _operator_context(operator, lead_name, text):
    parts = []
    codename = frappe.db.get_value("Investigator", operator, "codename")
    parts.append("Operatore: " + operator + (f" ({codename})" if codename else ""))
    refs = []
    lc = frappe.db.get_value("Intel Lead", lead_name, "linked_case")
    if lc:
        refs.append(lc)
    for tok in re.findall(r"CASE-\d{4}-\d+", text or "", re.I):
        tok = tok.upper()
        if tok not in refs and frappe.db.exists("Investigation Case", tok):
            refs.append(tok)
    for cn in refs[:3]:
        parts.append(_case_brief(cn))
    rec = frappe.get_all("Investigation Case",
                         fields=["name", "case_title", "status", "case_type"],
                         order_by="modified desc", limit=8)
    if rec:
        parts.append("Casi recenti:\n" + "\n".join(
            f"- {c.name} [{c.status}] {c.case_type or ''}: {c.case_title}" for c in rec))
    return "\n\n".join(parts)


_CASE_MENTION_RE = re.compile(
    r"(?:\bCASE-(\d{4})-(\d+)\b)|"       # CASE-2026-0010
    r"(?:\bcas[oei]?\s+(\d{4})-(\d+)\b)|"  # caso 2026-0010
    r"(?:\bcas[oei]?\s+(\d{1,5})\b)",     # caso 10, caso 0010
    re.I,
)


def _resolve_case(lead_name, text):
    """Caso di riferimento per i comandi operativi. Priorità:
       1) caso citato esplicitamente nel messaggio (CASE-YYYY-N, o formati
          abbreviati: 'caso 2026-0010', 'caso 10', 'caso 0010', ecc.)
       2) altrimenti il linked_case della chat
    L'ordine è importante: se sto in una chat agganciata al caso X ma scrivo
    'sul caso 0010', il target è 0010."""
    from frappe.utils import today
    current_year = today().split("-")[0]

    for m in _CASE_MENTION_RE.finditer(text or ""):
        y_full, n_full, y_short, n_short, n_only = m.groups()
        candidates = []
        if y_full and n_full:
            candidates.append(f"CASE-{y_full}-{n_full}")
        elif y_short and n_short:
            candidates.append(f"CASE-{y_short}-{n_short}")
        elif n_only:
            n = n_only.zfill(4)
            candidates.append(f"CASE-{current_year}-{n}")
            # se non esiste, prova anni indietro
            for y in range(int(current_year) - 1, int(current_year) - 4, -1):
                candidates.append(f"CASE-{y}-{n}")
        for c in candidates:
            c = c.upper()
            if frappe.db.exists("Investigation Case", c):
                return c
    return frappe.db.get_value("Intel Lead", lead_name, "linked_case")


@frappe.whitelist()
def operator_assistant_reply(lead_name, wa_phone, sender, text, operator):
    """Co-pilota AI operativo su WhatsApp. Se la chat è agganciata a un caso (o il
    messaggio cita un CASE-…), il messaggio passa all'assistente del caso che ESEGUE
    gli strumenti reali (visura camerale, soci/UBO, screening KYC/PEP/sanzioni,
    negatività, patrimoniale, dossier, proforma, fascicolo, doppia cessione, domande,
    cluster, analisi completa…) e risponde con l'esito — non è un semplice chatbot.
    Senza caso, risponde col contesto (lead/casi recenti)."""
    # Contesto conversazionale: la history recente della chat WA cosi'
    # il brain non "perde la chat" tra un messaggio e l'altro
    try:
        from thanatos_intel.ingest.wa_bot import _history
        convo = _history(lead_name)
    except Exception:
        convo = ""
    contextualized = ((f"Storico conversazione WhatsApp con l'operatore:\n{convo}\n\n"
                       f"Nuovo messaggio dell'operatore: {text}") if convo else text)

    case = _resolve_case(lead_name, text)
    if case:
        try:
            from thanatos_intel.ai.case_assistant import case_ai_chat
            r = case_ai_chat(case, contextualized) or {}
            out = (r.get("reply") or "").strip()
            if out:
                _reply(wa_phone, sender, lead_name, out)
                return {"ok": True, "case": case, "action": r.get("action")}
        except Exception:
            frappe.log_error(frappe.get_traceback(), "operator case_ai_chat")
    # senza caso → cervello operativo globale (stessi strumenti/contesto del desk)
    resp = None
    try:
        from thanatos_intel.ai.ops_brain import answer as ops_answer
        # session_id stabile per lead+operatore = coerenza tra turni
        out = (ops_answer(contextualized, operator=operator, lead_name=lead_name,
                          session_id=f"op-{operator}-{lead_name}") or "").strip()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator ops_brain")
        out = ""
    if not out:
        from thanatos_intel.ai.doc_ingest import _gateway
        from thanatos_intel.ai.case_architect import _resp_text
        ctx = _operator_context(operator, lead_name, text)
        msg = (f"Contesto operativo:\n{ctx}\n\n"
               f"Messaggio dell'operatore: «{text}»\n\nRispondi all'operatore.")
        resp = _gateway(msg, system=_OP_SYS, task_type="chat", session_id=f"op-{operator}")
        out = (_resp_text(resp) or "").strip()
    if not out:
        out = "Ricevuto. (assistente AI momentaneamente non disponibile)"
    _reply(wa_phone, sender, lead_name, out)
    try:
        usage = (resp or {}).get("usage") or {}
        if usage.get("tokens_in") or usage.get("tokens_out"):
            from thanatos_intel.billing.ai_meter import record_usage
            record_usage(client=None, model=(resp or {}).get("model", "default"),
                         tokens_in=usage.get("tokens_in", 0),
                         tokens_out=usage.get("tokens_out", 0), reference=lead_name)
    except Exception:
        pass
    return {"ok": True}


_DOC_EXT = (".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".tiff", ".tif")


def _lead_documents(lead_name):
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Intel Lead", "attached_to_name": lead_name},
        fields=["name", "file_name", "file_url"],
        order_by="creation asc", limit=0,
    )
    out, seen = [], set()
    for f in files:
        if not (f.file_name or "").lower().endswith(_DOC_EXT):
            continue
        key = (f.file_url or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


_CLASSIFY_SYS = (
    "Sei un analista di Thanatos Intel. Ricevi l'elenco dei nomi dei documenti di una "
    "nuova pratica investigativa. Scegli il tipo di caso piu' adatto SOLO tra questi: "
    "{types}. Rispondi SOLO con JSON valido, nessun testo fuori dal JSON: "
    '{{"case_type":"<uno dei tipi elencati>","case_title":"titolo breve in italiano",'
    '"summary":"2 frasi di sintesi"}}'
)


def _classify_case(doc_names, case_types):
    from thanatos_intel.ai.doc_ingest import _gateway, _extract_json
    from thanatos_intel.ai.case_architect import _resp_text
    sys = _CLASSIFY_SYS.format(types=", ".join(case_types))
    msg = ("Documenti della pratica:\n- " + "\n- ".join(doc_names) +
           "\n\nRispondi SOLO con il JSON richiesto.")
    resp = _gateway(msg, system=sys, task_type="chat")
    return _extract_json(_resp_text(resp)) or {}


_BOX_CASES = "/mnt/thanatos-box/Cases"
_MIME = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "webp": "image/webp", "tiff": "image/tiff",
         "tif": "image/tiff", "txt": "text/plain",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _ensure_case_box(case):
    """Garantisce che la cartella Drive del caso viva nel box dedicato
    (/mnt/thanatos-box/Cases/<CASE>), sostituendo la dir locale con un symlink.
    Idempotente. Ritorna il path box o None."""
    import os
    import shutil
    folder = frappe.db.get_value("Investigation Case", case, "drive_folder")
    rel = frappe.db.get_value("Drive File", folder, "path") if folder else None
    if not rel:
        return None
    local = frappe.get_site_path("private", "files", rel.rstrip("/"))
    box = os.path.join(_BOX_CASES, case)
    try:
        if os.path.islink(local):
            return os.path.realpath(local)
        if not os.path.isdir("/mnt/thanatos-box"):
            return None
        os.makedirs(box, exist_ok=True)
        if os.path.isdir(local):
            for entry in os.listdir(local):
                s, d = os.path.join(local, entry), os.path.join(box, entry)
                if not os.path.exists(d):
                    shutil.move(s, d)
            shutil.rmtree(local, ignore_errors=True)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        os.symlink(box, local)
        return box
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator _ensure_case_box")
        return None


def _consolidate_to_box(local, box_copy):
    """Ri-punta il file/symlink locale del lead alla copia nel box del caso e rimuove
    la vecchia copia orfana (es. attachments/intel_lead/...). Una sola copia fisica."""
    import os
    try:
        if not (box_copy and os.path.isfile(box_copy)):
            return
        old_target = os.path.realpath(local) if os.path.islink(local) else None
        if old_target == box_copy:
            return  # già consolidato
        # sicurezza: stessa dimensione prima di sostituire
        cur = local if os.path.exists(local) else None
        if cur and os.path.getsize(os.path.realpath(local)) != os.path.getsize(box_copy):
            return
        if os.path.lexists(local):
            os.remove(local)
        os.symlink(box_copy, local)
        # rimuovi la copia box orfana (solo sotto /mnt/thanatos-box/attachments/)
        if (old_target and old_target != box_copy
                and old_target.startswith("/mnt/thanatos-box/attachments/")
                and os.path.isfile(old_target)):
            os.remove(old_target)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator _consolidate_to_box")


def archive_lead_docs_to_case(case, lead_name):
    """Archivia i documenti del lead nella cartella Drive del caso (box dedicato),
    sottocartella '01 Documenti'. Dopo l'archiviazione consolida: una sola copia
    fisica nel box del caso, l'allegato del lead diventa symlink a quella copia,
    le copie orfane (attachments/intel_lead) vengono rimosse. Idempotente."""
    import os
    from thanatos_intel.reporting.case_reports import _put_in_drive, _client_name
    _ensure_case_box(case)
    client = _client_name(frappe.get_doc("Investigation Case", case))
    n = 0
    for d in _lead_documents(lead_name):
        local = frappe.get_site_path("private", "files", (d.file_url or "").split("/files/")[-1])
        if not os.path.exists(local):
            continue
        ext = (d.file_name or "").rsplit(".", 1)[-1].lower()
        mime = _MIME.get(ext, "application/octet-stream")
        try:
            with open(local, "rb") as fh:
                drive_name = _put_in_drive(case, d.file_name, fh.read(), mime, client,
                                           subfolder="01 Documenti")
            if drive_name:
                rel = frappe.db.get_value("Drive File", drive_name, "path")
                box_copy = os.path.realpath(
                    frappe.get_site_path("private", "files", rel)) if rel else None
                _consolidate_to_box(local, box_copy)
            n += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator archive doc {d.file_name}")
    return n


@frappe.whitelist()
def run_open_case(lead_name, wa_phone=None, sender=None, operator=None):
    """Job: crea un Investigation Case dai documenti allegati al lead e li ingerisce."""
    docs = _lead_documents(lead_name)
    if not docs:
        _reply(wa_phone, sender, lead_name,
               "⚠️ Non trovo allegati su questa conversazione. Inviami prima "
               "i documenti, poi ripeti il comando.")
        return {"ok": False, "reason": "no documents"}

    from thanatos_intel.ai.doc_ingest import ingest_document

    case_types = [r.name for r in frappe.get_all("Case Type", limit=0)]
    cls = _classify_case([d.file_name for d in docs], case_types)
    ctype = cls.get("case_type") if cls.get("case_type") in case_types else (
        "Due Diligence" if "Due Diligence" in case_types else
        (case_types[0] if case_types else None))
    title = (cls.get("case_title") or f"Pratica WhatsApp {now_datetime():%d/%m %H:%M}")[:140]

    case = frappe.new_doc("Investigation Case")
    case.case_title = title
    if ctype:
        case.case_type = ctype
    case.status = "Open"
    case.priority = "High"
    case.opening_date = now_datetime()
    case.description = (cls.get("summary") or "")[:2000]
    case.summary = (cls.get("summary") or "")[:1000]
    case.insert(ignore_permissions=True)
    frappe.db.commit()

    # archivia i documenti nella cartella Drive del caso (box dedicato)
    try:
        archive_lead_docs_to_case(case.name, lead_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator archive_lead_docs")

    results = []
    for d in docs:
        try:
            r = ingest_document(file_url=d.file_url, investigation_case=case.name,
                                document_type="generic") or {}
            ex = r.get("extracted") or {}
            results.append({"file": d.file_name, "summary": ex.get("summary", ""),
                            "flags": ex.get("risk_flags") or [],
                            "entities": ex.get("entities") or [],
                            "authenticity": r.get("authenticity") or "Non determinabile",
                            "evidence": r.get("evidence")})
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator ingest {d.file_name}")
            results.append({"file": d.file_name, "summary": "(errore analisi)", "flags": [],
                            "entities": [], "authenticity": "Non determinabile"})
        frappe.db.commit()

    # anagrafica ISO: registra TUTTE le parti come entità + crea l'anagrafica cliente
    all_entities = [e for r in results for e in (r.get("entities") or [])]
    n_parties = 0
    try:
        n_parties = _register_parties(case.name, all_entities)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator register_parties")
    try:
        _ensure_case_client(case.name, lead_name, sender)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator ensure_client")

    op_user = _operator_user(operator)
    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        lead.db_set("linked_case", case.name, notify=False)
        lead.db_set("status", "Promosso a Caso", notify=False)
        lead.db_set("promoted_at", now_datetime(), notify=False)
        lead.db_set("promoted_by", op_user, notify=False)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator link case")

    n_flags = sum(len(r.get("flags") or []) for r in results)
    suspect = [r for r in results if r.get("authenticity") in ("Dubbio", "Manomesso", "Contraffatto")]
    lines = [f"✅ Pratica aperta: *{case.name}*",
             f"{title}",
             f"Tipo: {ctype or 'n/d'} · {len(results)} documenti analizzati"]
    if n_flags:
        lines.append(f"⚠️ {n_flags} red flag rilevati")
    if suspect:
        lines.append(f"\U0001F50E {len(suspect)} documenti con autenticità non confermata "
                     "(dubbio/manomesso/contraffatto)")
    if n_parties:
        lines.append(f"\U0001F465 {n_parties} parti identificate e schedate (entità)")
    lines.append("\U0001F4E6 documenti archiviati nel box del caso")
    lines.append("")
    _AICON = {"Autentico": "✅", "Dubbio": "❓", "Manomesso": "⚠️",
              "Contraffatto": "⛔", "Non determinabile": "▫️"}
    for r in results[:12]:
        s = (r.get("summary") or "").strip().replace("\n", " ")
        ic = _AICON.get(r.get("authenticity"), "▫️")
        lines.append(f"{ic} {r['file']}: {s[:130]}" if s else f"{ic} {r['file']}")
    if len(results) > 12:
        lines.append(f"… e altri {len(results) - 12} documenti")
    lines.append("")
    lines.append(f"\U0001F517 {get_url('/app/investigation-case/' + case.name)}")
    _reply(wa_phone, sender, lead_name, "\n".join(lines))

    # automazione: lancia l'intera pipeline analitica in background (screening, doppia
    # cessione, domande, riconciliazione fatture, fascicolo, checklist)
    try:
        frappe.enqueue("thanatos_intel.ai.case_orchestrator.run_full_analysis",
                       queue="long", timeout=2400, case=case.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "enqueue full analysis")

    _notify_desk(lead_name, case.name, op_user, len(results), n_flags)
    return {"ok": True, "case": case.name, "documents": len(results), "flags": n_flags}


_ENTITY_TYPE = {"person": "Person", "company": "Company"}


def _register_parties(case_name, entities):
    """Schedatura ISO: ogni parte (persona/azienda) diventa una Investigation Entity
    collegata al caso (Case Entity). Dedup per nome+tipo. Ritorna n. nuove parti."""
    case = frappe.get_doc("Investigation Case", case_name)
    linked = {ce.entity for ce in (case.get("case_entities") or [])}
    seen, created = set(), 0
    for e in entities or []:
        etype = _ENTITY_TYPE.get((e.get("type") or "").lower())
        name = (e.get("name") or "").strip()
        norm = re.sub(r"[^\w\s]", "", name.lower())
        norm = re.sub(r"\b(s\s*r\s*l|srl|spa|s\s*p\s*a|snc|sas|srls)\b", "", norm)
        norm = re.sub(r"\s+", " ", norm).strip()
        key = (etype, norm)
        if not etype or len(name) < 3 or key in seen:
            continue
        seen.add(key)
        ent = frappe.db.get_value("Investigation Entity",
                                  {"full_name": name, "entity_type": etype}, "name")
        if not ent:
            doc = frappe.get_doc({"doctype": "Investigation Entity", "entity_type": etype,
                                  "full_name": name, "primary_identifier": name,
                                  "status": "Active"})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            ent = doc.name
        if ent not in linked:
            case.append("case_entities", {"entity": ent, "entity_type": etype,
                                          "role_in_case": "Subject",
                                          "notes": (e.get("role") or "")[:140]})
            linked.add(ent)
            created += 1
    if created:
        case.save(ignore_permissions=True)
        frappe.db.commit()
    return created


def _ensure_case_client(case_name, lead_name, sender):
    """Crea/collega l'anagrafica cliente del caso con KYC/KYB da completare.
    Se il mittente è un operatore (caso aperto per conto terzi) crea un placeholder
    «da identificare»; altrimenti usa i dati del lead. ISO: il cliente va sempre
    identificato (KYC/KYB)."""
    case = frappe.get_doc("Investigation Case", case_name)
    if case.get("client"):
        return case.client
    is_operator = bool(find_operator(sender))
    src_name = frappe.db.get_value("Intel Lead", lead_name, "source_name") or ""
    phone = "" if is_operator else (frappe.db.get_value("Intel Lead", lead_name,
                                                        "source_identifier") or "")
    cl = frappe.db.get_value("Investigation Client", {"phone": phone}, "name") if phone else None
    if not cl:
        cname = (src_name if (src_name and not is_operator)
                 else f"Cliente da identificare ({case_name})")
        # Investigation Client si autonamina sull'email → sempre una email valida
        email = (f"wa-{_digits(phone)}@lead.thanatos.agency" if phone
                 else f"caso-{case_name.lower()}@daidentificare.thanatos.agency")
        if frappe.db.exists("Investigation Client", email):
            cl = email
        else:
            doc = frappe.get_doc({"doctype": "Investigation Client", "client_name": cname[:140],
                                  "client_type": "Company", "email": email, "phone": phone,
                                  "onboarding_status": "Pending KYC",
                                  "kyc_status": "Not Started", "kyb_status": "Not Started"})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
            cl = doc.name
    case.db_set("client", cl, notify=False)
    frappe.db.commit()
    return cl


def send_document_wa(wa_phone, to_number, content, filename, caption, lead_name):
    """Invia un PDF/documento via WhatsApp Cloud API (upload media + invio)."""
    from frappe.utils.password import get_decrypted_password
    import requests
    from thanatos_intel.ingest.wa_bot import _wa_doc
    wd = _wa_doc(wa_phone)
    if not wd:
        return False
    pnid = wd.meta_phone_number_id
    token = get_decrypted_password("WhatsApp Number", wd.name, "meta_access_token")
    if not (pnid and token):
        return False
    to_clean = (to_number or "").lstrip("+").replace(" ", "").replace("-", "")
    mime = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if filename.lower().endswith(".docx") else "application/pdf")
    try:
        up = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/media",
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, content, mime)},
            headers={"Authorization": f"Bearer {token}"}, timeout=120)
        mid = (up.json() or {}).get("id")
        if not mid:
            frappe.log_error((up.text or "")[:500], "wa send_document upload")
            return False
        r = requests.post(
            f"https://graph.facebook.com/v21.0/{pnid}/messages",
            json={"messaging_product": "whatsapp", "recipient_type": "individual",
                  "to": to_clean, "type": "document",
                  "document": {"id": mid, "filename": filename, "caption": (caption or "")[:900]}},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30)
        return r.status_code == 200 and bool((r.json() or {}).get("messages"))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "wa send_document")
        return False


def _relazione_text(case):
    c = frappe.get_doc("Investigation Case", case)
    client = (frappe.db.get_value("Investigation Client", c.client, "client_name") if c.client else None) or "Cliente"
    n_ev = frappe.db.count("Investigation Evidence", {"investigation_case": case})

    def act(*needles):
        rows = frappe.get_all("Case Activity", filters={"parent": case}, fields=["description"],
                              order_by="activity_date asc", limit=0)
        for r in rows:
            d = (r.description or "")
            if any(n.lower() in d.lower() for n in needles):
                return d
        return ""

    parts = []
    parts.append(f"📑 *RELAZIONE INVESTIGATIVA — {c.name}*\n{c.case_title}\nCliente: {client}\n")
    parts.append("*1. Sintesi*\nIl cliente ha acquistato crediti d'imposta ceduti da BOMAX S.R.L. versando "
                 "~€800.000. Le verifiche indicano gravi anomalie sulla genuinità dei crediti e dei documenti "
                 "(l'AdE avrebbe già segnalato la non spettanza).")
    dc = act("DOPPIA CESSIONE")
    if dc:
        parts.append("*2. Doppia cessione*\n" + dc)
    ff = act("Fattorelli")
    if ff:
        parts.append("*3. Asseverazione Fattorelli (6869)*\n" + ff)
    deb = act("DICHIARAZIONE FATTURE", "Debitori")
    if deb:
        parts.append("*4. Fatture/debitori*\n" + deb)
    th = act("Contratto cessione DTA BOMAX")
    if th:
        parts.append("*5. Contratto del cliente (Trading HU)*\n" + th)
    parts.append("*6. Documenti e custodia*\n" + f"{n_ev} reperti analizzati, con verdetto di autenticità e "
                 "hash SHA-256 (catena di custodia). Dettaglio nel Dossier e nel Fascicolo allegati.")
    parts.append("*7. Conclusioni*\nCrediti e fatture a base del DTA appaiono fabbricati/gonfiati. Prossimi passi: "
                 "delega del cliente → cassetto/fatture AdE + tracciamento dei bonifici (€800.000); valutazione "
                 "denuncia (truffa/falso/fatture inesistenti) e azione civile/recupero verso cedente, intermediari "
                 "e asseveratori (escussione RC).")
    ass = act("INDENNIZZO ASSICURATIVO")
    if ass:
        parts.append("*8. Indennizzo assicurativo*\n" + ass)
    mnd = frappe.db.get_value("Agency Mandate", {"investigation_case": case}, "name")
    parts.append("*9. Atti predisposti (in allegato)*\nMandato d'incarico"
                 + (f" {mnd}" if mnd else "") + " (bozza), preventivo € 26.000, dossier cliente, "
                 "fascicolo integrale, formulario investigativo e delega AdE.")
    return parts


@frappe.whitelist()
def send_case_report_wa(case, lead_name, wa_phone, sender, include_pdf=1):
    """Invia su WhatsApp l'intera relazione del caso (testo a sezioni) + i PDF chiave."""
    sections = _relazione_text(case)
    # invio a sezioni, rispettando il limite WhatsApp
    chunk = ""
    sent = 0
    for sec in sections:
        piece = sec + "\n\n"
        if len(chunk) + len(piece) > 3500:
            _reply(wa_phone, sender, lead_name, chunk.strip())
            sent += 1
            chunk = ""
        chunk += piece
    if chunk.strip():
        _reply(wa_phone, sender, lead_name, chunk.strip())
        sent += 1
    docs_sent = 0
    if int(include_pdf):
        import os

        def _send_path(path, fname, label):
            if not (path and os.path.exists(path)):
                return False
            with open(path, "rb") as fh:
                return send_document_wa(wa_phone, sender, fh.read(), fname, label, lead_name)

        for like, label in [("DOSSIER CLIENTE", "Dossier cliente"), ("PROFORMA", "Preventivo (€26.000)"),
                            ("FORMULARIO", "Formulario investigativo"), ("DELEGA AdE", "Delega AdE"),
                            ("FASCICOLO", "Fascicolo integrale")]:
            fr = frappe.db.get_value("File", {"attached_to_doctype": "Investigation Case",
                                              "attached_to_name": case, "file_name": ["like", f"%{like}%"]},
                                     ["file_name", "file_url"], as_dict=True)
            if not fr:
                continue
            path = frappe.get_site_path("private", "files", (fr.file_url or "").split("/files/")[-1])
            if _send_path(path, fr.file_name, label):
                docs_sent += 1
        # mandato d'incarico (PDF generato dal doc Agency Mandate)
        mnd = frappe.db.get_value("Agency Mandate", {"investigation_case": case}, "name")
        if mnd:
            pdf_url = frappe.db.get_value("Agency Mandate", mnd, "mandate_pdf")
            if not pdf_url:
                try:
                    from thanatos_intel.thanatos_ddd.pdf.mandate import generate_mandate_pdf
                    generate_mandate_pdf(mnd)
                    pdf_url = frappe.db.get_value("Agency Mandate", mnd, "mandate_pdf")
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "wa mandate pdf")
            if pdf_url:
                path = frappe.get_site_path("private", "files", (pdf_url or "").split("/files/")[-1])
                if _send_path(path, f"Mandato {mnd}.pdf", "Mandato d'incarico (bozza)"):
                    docs_sent += 1
    return {"ok": True, "messaggi": sent, "documenti": docs_sent}


def _reply(wa_phone, to_number, lead_name, body):
    if not (wa_phone and to_number):
        return
    try:
        from thanatos_intel.ingest.wa_bot import _wa_doc, send_text
        wd = _wa_doc(wa_phone)
        if wd:
            send_text(wd, to_number, body, lead_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator reply")


def _notify_desk(lead_name, case, operator, ndocs, nflags):
    try:
        from thanatos_intel.ingest.intel_notifications import _notify
        msg = (f"{case}: {ndocs} documenti analizzati"
               + (f", {nflags} red flag" if nflags else ""))
        _notify(operator or "Administrator", "Pratica aperta da WhatsApp", msg,
                lead_name, "orange" if nflags else "green")
    except Exception:
        pass


def _has_summary(notes):
    return bool(notes and "Sintesi AI" in notes and len(notes) > 80)


def _reprocess_evidence(ev):
    """Ri-OCR + ri-estrae un reperto e aggiorna note/nome in place.
    Ritorna (ok, summary)."""
    import json
    from thanatos_intel.ai.ocr_service import ocr_file
    from thanatos_intel.ai.doc_ingest import (_gateway, _extract_json, _normalize,
                                              _read_text_fallback, EXTRACT_SYSTEM)
    from thanatos_intel.ai.case_architect import _resp_text
    fu = ev.get("attached_file")
    if not fu:
        return False, ""
    try:
        ocr = ocr_file(fu, "generic") or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reprocess ocr")
        ocr = {}
    text = (ocr.get("raw_text") or "").strip() or (_read_text_fallback(fu) or "").strip()
    if not text:
        return False, ""
    ai = _gateway(f"Testo del documento:\n\n{text[:12000]}", system=EXTRACT_SYSTEM,
                  task_type="extract")
    parsed = _normalize(_extract_json(_resp_text(ai)))
    if not parsed:
        return False, ""
    note_lines = ["— Sintesi AI —", parsed.get("summary") or ""]
    if parsed.get("risk_flags"):
        note_lines.append("Red flag: " + "; ".join(parsed["risk_flags"]))
    if parsed.get("key_fields"):
        note_lines.append("Campi: " + json.dumps(parsed["key_fields"], ensure_ascii=False))
    note_lines.append(f"OCR provider: {ocr.get('provider')} · confidenza: {ocr.get('confidence')}")
    frappe.db.set_value("Investigation Evidence", ev["name"], {
        "notes": "\n".join(x for x in note_lines if x),
        "evidence_name": (parsed.get("document_type", "Documento") or "Documento") + " — AI ingest",
    })
    frappe.db.commit()
    return True, (parsed.get("summary") or "")


# ─── Helper testuali e listing ───────────────────────────────────────────────

def _int_in(text, label, default):
    m = re.search(r"\b" + label + r"\s*[:=]?\s*(\d{1,4})", text or "", re.I)
    return int(m.group(1)) if m else default


def _help_text(operator):
    role = _operator_role(operator)
    lines = [
        f"Ciao — sei loggato come *{operator or '?'}* (ruolo: {role}).",
        "Comandi che posso eseguire dalla chat:",
        "",
        "📂 *Pratica*",
        "• «*apri un caso*» (con allegati) → apro pratica + analizzo i documenti",
        "• «*aggiungi al caso CASE-…*» (con allegati) → li aggiungo come reperti",
        "• «*rileggi i documenti*» → rifaccio OCR + estrazione",
        "• «*fai le domande*» → domande investigative per ogni reperto",
        "• «*stato CASE-…*» / «*riassumi CASE-…*» → sintesi della pratica",
        "• «*documenti*» (in chat agganciata a un caso) → elenco reperti",
        "",
        "💶 *Cliente / fatturazione*",
        "• «*proforma CASE-…*» → genero il preventivo, te lo mando per revisione",
        "• «*proforma e manda al cliente CASE-…*» → genero e invio al cliente",
        "• «*pagamento CASE-…*» → link Stripe al cliente per lo step pagabile corrente",
        "• «*manda al cliente CASE-…*» → consegno relazione + documenti chiave al cliente",
    ]
    if _ROLE_RANK.get(role, 0) >= _ROLE_RANK["admin"]:
        lines += [
            "",
            "🛡 *Amministrazione*",
            "• «*chiudi il caso CASE-…*»",
            "• «*assegna a <Nome Cognome> CASE-…*»",
        ]
    if role != "super_admin":
        lines += [
            "",
            "Le modifiche tecniche (settings, doctype, integrazioni) sono riservate al super-admin.",
        ]
    lines += ["", "Qualsiasi altro messaggio: te lo gestisco col co-pilota AI."]
    return "\n".join(lines)


def _docs_list(case):
    evs = frappe.get_all("Investigation Evidence",
                         filters={"investigation_case": case},
                         fields=["evidence_name", "attached_file", "notes"],
                         order_by="creation asc", limit=0)
    if not evs:
        return f"📦 Caso *{case}*: nessun reperto caricato."
    lines = [f"📦 Reperti caso *{case}* ({len(evs)}):"]
    for i, e in enumerate(evs[:25], 1):
        fname = (e.attached_file or "").split("/files/")[-1] or e.evidence_name
        summ = ""
        if e.notes and "Sintesi AI" in e.notes:
            after = e.notes.split("Sintesi AI", 1)[-1].strip(" —\n")
            summ = " — " + after.replace("\n", " ")[:90]
        lines.append(f"{i:2d}. {fname}{summ}")
    if len(evs) > 25:
        lines.append(f"… e altri {len(evs) - 25} reperti")
    lines.append("")
    lines.append("🔗 " + get_url("/app/investigation-case/" + case))
    return "\n".join(lines)


# ─── Job: proforma → cliente o operatore ─────────────────────────────────────

@frappe.whitelist()
def run_send_proforma(case, lead_name, wa_phone, sender, operator,
                      hours_senior=40, hours_analyst=30, sconto=0,
                      send_to_client=0):
    """Genera la proforma del caso e la manda al cliente del caso (se richiesto)
    o all'operatore richiedente per revisione."""
    try:
        from thanatos_intel.billing.proforma_cliente import genera_proforma
        r = genera_proforma(case, hours_senior=int(hours_senior),
                            hours_analyst=int(hours_analyst), sconto=int(sconto)) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator proforma generate")
        _reply(wa_phone, sender, lead_name,
               "⚠️ Non sono riuscito a generare la proforma — controlla il caso.")
        return {"ok": False, "reason": "generate failed"}

    file_url = r.get("file_url")
    importo = r.get("imponibile") or 0
    if not file_url:
        _reply(wa_phone, sender, lead_name,
               "⚠️ Proforma generata ma file non trovato.")
        return {"ok": False, "reason": "no file"}

    import os
    local = frappe.get_site_path("private", "files",
                                 file_url.split("/files/")[-1])
    if not os.path.exists(local):
        _reply(wa_phone, sender, lead_name,
               f"⚠️ Proforma creata in DB ma file fisico mancante: {file_url}")
        return {"ok": False, "reason": "file missing on disk"}
    with open(local, "rb") as fh:
        content = fh.read()
    fname = f"Preventivo {case}.pdf"
    caption = (f"Preventivo Thanatos Intel per la pratica {case}. "
               f"Imponibile €{importo:,.0f} (IVA esclusa ove dovuta). "
               "Validità 30 giorni.").replace(",", ".")

    if int(send_to_client):
        ok = _send_doc_to_client(case, content, fname, caption)
        if ok:
            _reply(wa_phone, sender, lead_name,
                   f"✅ Proforma *{case}* inviata al cliente. Imponibile €{importo:,.0f}.\n"
                   f"📄 {get_url(file_url)}")
        else:
            # fallback: mandala all'operatore
            send_document_wa(wa_phone, sender, content, fname,
                             caption + "\n\n⚠️ Non ho trovato un canale WA col cliente — "
                             "te la mando a te.", lead_name)
            _reply(wa_phone, sender, lead_name,
                   "ℹ️ Cliente WA non trovato sul caso, ti ho mandato io la proforma.")
        return {"ok": True, "sent_to": "client" if ok else "operator"}
    # default: la riceve l'operatore
    send_document_wa(wa_phone, sender, content, fname, caption, lead_name)
    _reply(wa_phone, sender, lead_name,
           f"📎 Proforma *{case}* pronta. Imponibile €{importo:,.0f}.\n"
           "Rispondi «*proforma e manda al cliente " + case
           + "*» per inviarla al cliente.")
    return {"ok": True, "sent_to": "operator"}


# ─── Job: link pagamento → cliente ───────────────────────────────────────────

@frappe.whitelist()
def run_send_payment_link(case, lead_name, wa_phone, sender, operator):
    """Genera il link Stripe per lo step pagabile corrente del caso e lo manda al
    cliente. Se non ci sono step «pay» pendenti, avvisa l'operatore."""
    try:
        from thanatos_intel.integrations.stripe_bridge import create_case_step_checkout
        r = create_case_step_checkout(case) or {}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "operator payment link")
        _reply(wa_phone, sender, lead_name,
               f"⚠️ Non sono riuscito a generare il link di pagamento: {str(e)[:200]}")
        return {"ok": False, "reason": str(e)}

    url = r.get("url") or r.get("checkout_url")
    if not url:
        # caso a credito → già attivato
        if r.get("credit") or r.get("ok"):
            _reply(wa_phone, sender, lead_name,
                   f"✅ Step di *{case}* attivato a credito (cliente a bonifico). "
                   "Nessun link da inviare.")
            return {"ok": True, "credit": True}
        _reply(wa_phone, sender, lead_name,
               "⚠️ Nessuno step pagabile pendente in questo caso, "
               "o link non generato. Controlla i case_steps.")
        return {"ok": False, "reason": "no payable step"}

    body = (f"Buongiorno, dal team Thanatos Intel.\n"
            f"Per proseguire con la pratica può effettuare il pagamento al seguente "
            f"link sicuro Stripe:\n\n{url}\n\n"
            "Riceverà ricevuta e fattura via email. Grazie.")
    sent = _send_to_client(case, body)
    if sent:
        _reply(wa_phone, sender, lead_name,
               f"✅ Link di pagamento inviato al cliente del caso *{case}*.\n🔗 {url}")
    else:
        _reply(wa_phone, sender, lead_name,
               "ℹ️ Cliente WA non trovato sul caso — link generato comunque:\n" + url)
    return {"ok": True, "url": url}


# ─── Job: consegna relazione + documenti chiave al cliente ───────────────────

@frappe.whitelist()
def run_deliver_to_client(case, sender, wa_phone, lead_name, operator):
    """Recapita al cliente del caso la relazione completa + documenti chiave
    (riusa send_case_report_wa, ma destinato al numero del cliente del caso, non
    al numero dell'operatore mittente)."""
    cwa, client_num, client_lead = _client_lead_phone(case)
    if not (cwa and client_num and client_lead):
        _reply(wa_phone, sender, lead_name,
               "⚠️ Non ho un canale WhatsApp del cliente per questo caso. "
               "Verifica il lead promosso.")
        return {"ok": False, "reason": "no client wa"}
    try:
        r = send_case_report_wa(case=case, lead_name=client_lead,
                                wa_phone=cwa, sender=client_num,
                                include_pdf=1) or {}
        n_msg = r.get("messaggi", 0)
        n_doc = r.get("documenti", 0)
        _reply(wa_phone, sender, lead_name,
               f"✅ Consegna al cliente del caso *{case}* completata: "
               f"{n_msg} messaggi, {n_doc} documenti.")
        return r
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "operator deliver_to_client")
        _reply(wa_phone, sender, lead_name,
               f"⚠️ Consegna interrotta: {str(e)[:200]}")
        return {"ok": False, "reason": str(e)}


@frappe.whitelist()
def reprocess_case_docs(case, lead_name=None, wa_phone=None, sender=None, only_failed=1):
    """Ri-legge i documenti di un caso con l'OCR (utile dopo che è stato corretto un
    documento o aggiunto un motore OCR). Default: solo i reperti senza sintesi."""
    only_failed = int(only_failed)
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["name", "evidence_name", "notes", "attached_file"], limit=0)
    todo = [e for e in evs if (not only_failed) or not _has_summary(e.get("notes"))]
    done, still = 0, 0
    summaries = []
    for e in todo:
        ok, summ = _reprocess_evidence(e)
        if ok:
            done += 1
            if summ:
                summaries.append((e.get("attached_file") or "").split("/files/")[-1] + ": "
                                 + summ.replace("\n", " ")[:120])
        else:
            still += 1
    if wa_phone and sender and lead_name:
        lines = [f"\U0001F501 Riletti {done}/{len(todo)} documenti del caso {case}."]
        if still:
            lines.append(f"⚠️ {still} ancora illeggibili (scansione di bassa qualità).")
        for s in summaries[:8]:
            lines.append("\U0001F4C4 " + s)
        _reply(wa_phone, sender, lead_name, "\n".join(lines))
    return {"ok": True, "reprocessed": done, "still_failed": still}


# ─── Job: aggiungi allegati recenti dell'operatore a un caso ─────────────────

# ── ingest link/wallet da messaggi testuali WA ───────────────────────────────
_BTC_RE = re.compile(r"\b((?:bc1[ac-hj-np-z02-9]{6,87})|(?:[13][a-km-zA-HJ-NP-Z1-9]{25,34}))\b")
_EVM_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_TRX_RE = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.I)
_CHAIN_OF = {"BTC": "Bitcoin", "EVM": "Ethereum", "TRX": "TRON"}


def _extract_links_wallets_from_lead(lead_name, minutes=1440):
    """Scansiona gli inbound testuali RECENTI (Communication) del lead e ne
    estrae URL e indirizzi wallet. Ritorna {wallets:[(addr,chain)], links:[url]}"""
    from frappe.utils import now_datetime, add_to_date
    since = add_to_date(now_datetime(), minutes=-int(minutes))
    # i messaggi WA vivono nel child `Intel Lead Message` (non in Communication).
    # Timestamp affidabile = sent_at (creation e' quello del parent).
    rows = frappe.db.sql("""
        SELECT content FROM `tabIntel Lead Message`
        WHERE parent=%s AND direction='Inbound' AND sent_at > %s
    """, (lead_name, since), as_dict=True)
    text = " \n ".join((r["content"] or "") for r in rows)
    # fallback: se il child non trova niente, prova il campo content del lead
    if not text.strip():
        text = frappe.db.get_value("Intel Lead", lead_name, "content") or ""
    wallets, seen_w = [], set()
    for addr in _BTC_RE.findall(text):
        if addr not in seen_w:
            wallets.append((addr, "BTC")); seen_w.add(addr)
    for addr in _EVM_RE.findall(text):
        if addr.lower() not in seen_w:
            wallets.append((addr, "EVM")); seen_w.add(addr.lower())
    for addr in _TRX_RE.findall(text):
        if addr not in seen_w:
            wallets.append((addr, "TRX")); seen_w.add(addr)
    links, seen_u = [], set()
    for url in _URL_RE.findall(text):
        url = url.rstrip(".,;)")
        if url not in seen_u:
            links.append(url); seen_u.add(url)
    return {"wallets": wallets, "links": links}


def _ingest_links_wallets(case, extract, operator):
    """Crea Investigation Entity per ogni wallet + Investigation Evidence per
    ogni link, li aggancia al caso. Idempotente."""
    added_w, added_l = [], []
    c = frappe.get_doc("Investigation Case", case)
    existing_entities = {ce.entity for ce in (c.case_entities or [])}
    for addr, chain in extract["wallets"]:
        if not frappe.db.exists("Investigation Entity", addr):
            try:
                frappe.get_doc({
                    "doctype": "Investigation Entity",
                    "primary_identifier": addr,
                    "entity_type": "Wallet",
                    "display_name": f"{_CHAIN_OF.get(chain, chain)}: {addr[:10]}…",
                }).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"create wallet entity {addr}")
                continue
        if addr not in existing_entities:
            c.append("case_entities", {"entity": addr, "role_in_case": "Subject",
                                       "notes": f"Wallet {chain} da WA"})
            existing_entities.add(addr)
        added_w.append(addr)
    if added_w:
        try:
            c.flags.ignore_mandatory = True
            c.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "save case wallets")

    for url in extract["links"]:
        try:
            frappe.get_doc({
                "doctype": "Investigation Evidence",
                "investigation_case": case,
                "evidence_name": f"Link WA: {url[:80]}",
                "evidence_type": "Document",
                "source": "WA operatore",
                "custody_status": "Received",
                "acquisition_date": now_datetime(),
                "notes": url,
            }).insert(ignore_permissions=True)
            added_l.append(url)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"evidence link {url[:60]}")
    frappe.db.commit()
    return {"wallets": added_w, "links": added_l}


@frappe.whitelist()
def run_add_docs_to_case(lead_name, case, wa_phone=None, sender=None,
                          operator=None, minutes=1440):
    """Prende i documenti allegati al lead operatore negli ultimi N minuti e li
    ingerisce come Investigation Evidence del caso indicato. Nessun re-download
    da Meta: usa i File Frappe già scaricati da _dispatch_media."""
    from frappe.utils import now_datetime, add_to_date
    from thanatos_intel.ai.doc_ingest import ingest_document

    if not frappe.db.exists("Investigation Case", case):
        _reply(wa_phone, sender, lead_name, f"⚠️ Caso {case} non trovato.")
        return {"ok": False, "reason": "case not found"}

    since = add_to_date(now_datetime(), minutes=-int(minutes))
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Intel Lead",
                 "attached_to_name": lead_name,
                 "creation": [">", since]},
        fields=["name", "file_name", "file_url"],
        order_by="creation asc", limit=0,
    )
    docs = [f for f in files if (f.file_name or "").lower().endswith(_DOC_EXT)]

    # Se non ci sono file, prova a estrarre link/wallet dai messaggi testuali
    # recenti (l'operatore ha mandato URL/indirizzi crypto, non PDF).
    if not docs:
        extra = _extract_links_wallets_from_lead(lead_name, minutes)
        if extra["wallets"] or extra["links"]:
            r = _ingest_links_wallets(case, extra, operator or "Administrator")
            body_lines = [f"✅ Aggiunti a *{case}*:"]
            if r["wallets"]:
                body_lines.append("")
                body_lines.append(f"💰 *{len(r['wallets'])} wallet* come Entity del caso:")
                body_lines += [f"- `{w}`" for w in r["wallets"][:12]]
                if len(r["wallets"]) > 12:
                    body_lines.append(f"… e altri {len(r['wallets']) - 12}")
            if r["links"]:
                body_lines.append("")
                body_lines.append(f"🔗 *{len(r['links'])} link* come reperti:")
                body_lines += [f"- {u}" for u in r["links"][:8]]
                if len(r["links"]) > 8:
                    body_lines.append(f"… e altri {len(r['links']) - 8}")
            body_lines.append("")
            body_lines.append("🔗 " + frappe.utils.get_url("/app/investigation-case/" + case))
            _reply(wa_phone, sender, lead_name, "\n".join(body_lines))
            return {"ok": True, "case": case, "wallets": len(r["wallets"]),
                    "links": len(r["links"])}
        _reply(wa_phone, sender, lead_name,
               f"Non trovo allegati né link/wallet nelle ultime {minutes // 60}h "
               f"per *{case}*. Mandami prima i documenti o gli indirizzi e ripeti.")
        return {"ok": False, "reason": "no recent content"}

    ok_n, fail_n = 0, 0
    lines = []
    for d in docs:
        try:
            r = ingest_document(file_url=d.file_url, investigation_case=case,
                                document_type="generic") or {}
            ex = r.get("extracted") or {}
            summ = (ex.get("summary") or "").replace("\n", " ")[:140]
            auth = r.get("authenticity") or ""
            icon = {"Autentico": "✅", "Dubbio": "❓", "Manomesso": "⚠️",
                    "Contraffatto": "⛔"}.get(auth, "📎")
            lines.append(f"{icon} {d.file_name}" + (f" — {summ}" if summ else ""))
            ok_n += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             f"add_docs_to_case ingest {d.file_name}")
            lines.append(f"⚠️ {d.file_name}: errore analisi")
            fail_n += 1
        frappe.db.commit()

    head = (f"✅ Aggiunti {ok_n} documenti a *{case}* come reperti"
            + (f" ({fail_n} falliti)" if fail_n else "") + ".")
    body = "\n".join([head, ""] + lines[:12])
    if len(lines) > 12:
        body += f"\n… e altri {len(lines) - 12} documenti"
    body += "\n\n🔗 " + frappe.utils.get_url("/app/investigation-case/" + case)
    _reply(wa_phone, sender, lead_name, body)
    return {"ok": True, "case": case, "added": ok_n, "failed": fail_n}
