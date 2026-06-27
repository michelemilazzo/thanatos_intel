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
    if _HELP_RE.search(t):
        _reply(wa_phone, sender, lead_name,
               "Comandi operatore:\n• invia i documenti, poi scrivi "
               "«*elabora gli allegati ed apri un caso*» → creo la "
               "pratica con i reperti gia' analizzati (OCR + AI).")
        return
    # nessun comando: messaggio operatore registrato e basta (lo legge dal Centralino)
    return


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


def _attach_to_case(file_row, case):
    try:
        if frappe.db.exists("File", {"file_url": file_row.file_url,
                                     "attached_to_doctype": "Investigation Case",
                                     "attached_to_name": case}):
            return
        is_priv = frappe.db.get_value("File", file_row.name, "is_private")
        frappe.get_doc({
            "doctype": "File", "file_url": file_row.file_url,
            "file_name": file_row.file_name, "is_private": is_priv,
            "attached_to_doctype": "Investigation Case", "attached_to_name": case,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator attach_to_case")


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

    results = []
    for d in docs:
        _attach_to_case(d, case.name)
        try:
            r = ingest_document(file_url=d.file_url, investigation_case=case.name,
                                document_type="generic") or {}
            ex = r.get("extracted") or {}
            results.append({"file": d.file_name, "summary": ex.get("summary", ""),
                            "flags": ex.get("risk_flags") or [],
                            "evidence": r.get("evidence")})
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"operator ingest {d.file_name}")
            results.append({"file": d.file_name, "summary": "(errore analisi)", "flags": []})
        frappe.db.commit()

    try:
        lead = frappe.get_doc("Intel Lead", lead_name)
        lead.db_set("linked_case", case.name, notify=False)
        lead.db_set("status", "Promosso a Caso", notify=False)
        lead.db_set("promoted_at", now_datetime(), notify=False)
        lead.db_set("promoted_by", operator or frappe.session.user, notify=False)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "operator link case")

    n_flags = sum(len(r.get("flags") or []) for r in results)
    lines = [f"✅ Pratica aperta: *{case.name}*",
             f"{title}",
             f"Tipo: {ctype or 'n/d'} · {len(results)} documenti analizzati"]
    if n_flags:
        lines.append(f"⚠️ {n_flags} red flag rilevati")
    lines.append("")
    for r in results[:12]:
        s = (r.get("summary") or "").strip().replace("\n", " ")
        lines.append(f"\U0001F4C4 {r['file']}: {s[:140]}" if s else f"\U0001F4C4 {r['file']}")
    if len(results) > 12:
        lines.append(f"… e altri {len(results) - 12} documenti")
    lines.append("")
    lines.append(f"\U0001F517 {get_url('/app/investigation-case/' + case.name)}")
    _reply(wa_phone, sender, lead_name, "\n".join(lines))

    _notify_desk(lead_name, case.name, operator, len(results), n_flags)
    return {"ok": True, "case": case.name, "documents": len(results), "flags": n_flags}


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
