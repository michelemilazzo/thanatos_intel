"""Investigatore digitale — domande investigative per ogni documento del caso.

Da ogni reperto genera 3-5 domande mirate, concrete e verificabili, per accertarne
autenticità, coerenza e i fatti rilevanti; le registra sul caso e le posta su
WhatsApp all'operatore. Lavora sulle sintesi già estratte (niente nuovo OCR).
"""
import frappe
from frappe.utils import now_datetime

from thanatos_intel.ai import doc_ingest as DI
from thanatos_intel.ai.case_architect import _resp_text

_SYS = (
    "Sei un investigatore digitale di Thanatos Intel (caso: due diligence su cessione di "
    "crediti d'imposta). Per il documento descritto genera 3-5 DOMANDE investigative "
    "mirate, concrete e VERIFICABILI, utili ad accertarne l'autenticità, la coerenza e i "
    "fatti rilevanti (chi, cosa verificare, dove, con quale fonte/ente). Niente premesse. "
    "Rispondi SOLO con JSON valido: {\"questions\": [\"...\", \"...\"]}. Italiano."
)


def _summary_of(notes):
    skip = ("Autenticità", "Red flag", "Campi", "OCR provider")
    for ln in (notes or "").split("\n"):
        ln = ln.strip()
        if ln and not ln.startswith("—") and not ln.startswith(skip):
            return ln
    return ""


def _questions_for(fname, auth, summary):
    msg = (f"Documento: {fname}\nVerdetto autenticità: {auth}\nSintesi: {summary}\n\n"
           "Genera le domande investigative.")
    ai = DI._gateway(msg, system=_SYS, task_type="chat")
    d = DI._extract_json(_resp_text(ai)) or {}
    return [q.strip() for q in (d.get("questions") or []) if isinstance(q, str) and q.strip()][:5]


@frappe.whitelist()
def generate_questions(case, lead_name=None, wa_phone=None, sender=None, post=1, notify_user=None):
    try:
        from thanatos_intel.ai.doc_ingest import _ensure_evidence_authfields
        _ensure_evidence_authfields()
    except Exception:
        pass
    evs = frappe.get_all("Investigation Evidence", filters={"investigation_case": case},
                         fields=["name", "evidence_name", "notes", "authenticity", "attached_file"],
                         order_by="creation asc", limit=0)
    blocks = []
    for e in evs:
        fn = (e.attached_file or e.evidence_name or "").split("/files/")[-1]
        qs = _questions_for(fn, e.authenticity or "N/D", _summary_of(e.notes))
        if qs:
            blocks.append((fn, e.authenticity or "N/D", qs))
            # salva le domande SUL reperto (per il percorso guidato per-documento)
            try:
                frappe.db.set_value("Investigation Evidence", e.name, "investigative_questions",
                                    "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1)))
            except Exception:
                pass
    frappe.db.commit()

    lines = ["🕵️ DOMANDE INVESTIGATIVE PER DOCUMENTO (investigatore digitale)"]
    for fn, auth, qs in blocks:
        lines.append(f"\n📄 {fn} [{auth}]")
        lines.extend(f"  {i}. {q}" for i, q in enumerate(qs, 1))
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(),
                 "activity_type": "Document Analysis",
                 "description": "\n".join(lines)[:1000], "operator": frappe.session.user})
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "doc_questions activity")

    sent = 0
    if int(post) and wa_phone and sender and lead_name:
        from thanatos_intel.ingest.operator_console import _reply
        chunk = "🕵️ *Domande investigative per documento*\n"
        for fn, auth, qs in blocks:
            piece = (f"\n📄 *{fn}* [{auth}]\n"
                     + "\n".join(f"  {i}. {q}" for i, q in enumerate(qs, 1)) + "\n")
            if len(chunk) + len(piece) > 3300:
                _reply(wa_phone, sender, lead_name, chunk)
                sent += 1
                chunk = ""
            chunk += piece
        if chunk.strip():
            _reply(wa_phone, sender, lead_name, chunk)
            sent += 1

    if notify_user:
        try:
            frappe.publish_realtime("msgprint", {
                "message": f"Domande investigative generate per {len(blocks)} documenti "
                           f"(caso {case}).", "indicator": "blue"}, user=notify_user)
        except Exception:
            pass
    return {"ok": True, "documents": len(blocks), "messages": sent}


@frappe.whitelist()
def generate_questions_async(case, lead_name=None, wa_phone=None, sender=None, post=1):
    frappe.enqueue("thanatos_intel.ai.doc_questions.generate_questions", queue="long",
                   timeout=1200, case=case, lead_name=lead_name, wa_phone=wa_phone,
                   sender=sender, post=post, notify_user=frappe.session.user)
    return {"queued": True}
