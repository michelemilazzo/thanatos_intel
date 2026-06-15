"""Comunicazioni al cliente — dentro Thanatos Intel.

Invia Email Template al cliente, collegando la mail al caso (timeline Comunicazioni).
Invio manuale (bottone sul caso) + automazioni su eventi (nuovo caso, mandato
firmato, report pronto). Template = Email Template con prefisso "Thanatos -".
"""
import frappe
from frappe import _

SENDER = "admin@thanatos.agency"


def _case_of(doc):
    """Risale al nome dell'Investigation Case da vari doctype."""
    if doc.doctype == "Investigation Case":
        return doc.name
    if doc.meta.has_field("investigation_case") and doc.get("investigation_case"):
        return doc.get("investigation_case")
    if doc.meta.has_field("linked_investigation_case") and doc.get("linked_investigation_case"):
        return doc.get("linked_investigation_case")
    if doc.meta.has_field("ddd_case") and doc.get("ddd_case"):
        return frappe.db.get_value("Diplomatic Eligibility Case", doc.ddd_case, "linked_investigation_case")
    return None


def _client_email(case_name):
    if not case_name:
        return None, None
    client = frappe.db.get_value("Investigation Case", case_name, "client")
    if not client:
        return None, None
    email = frappe.db.get_value("Investigation Client", client, "email")
    name = frappe.db.get_value("Investigation Client", client, "client_name") or client
    return email, name


def _send(case_name, template, ctx_doc=None):
    """Invia un template al cliente del caso, collegato al caso. Best-effort."""
    if not frappe.db.exists("Email Template", template):
        return False
    email, name = _client_email(case_name)
    if not email:
        return False
    tpl = frappe.get_doc("Email Template", template)
    ctx = {"client_name": name, "case": case_name, "doc": ctx_doc}
    frappe.sendmail(
        recipients=[email], sender=SENDER,
        subject=frappe.render_template(tpl.subject or "", ctx),
        message=frappe.render_template(tpl.response_html or tpl.response or "", ctx),
        reference_doctype="Investigation Case", reference_name=case_name,
    )
    return True


# ── API per il bottone manuale ───────────────────────────────────────
@frappe.whitelist()
def list_templates():
    return frappe.get_all("Email Template", filters={"name": ["like", "Thanatos -%"]}, pluck="name")


@frappe.whitelist()
def send_to_client(case, template):
    if not _send(case, template):
        frappe.throw(_("Impossibile inviare: il caso non ha un cliente con email, o template assente."))
    email, _n = _client_email(case)
    return {"ok": True, "to": email, "template": template}


# ── Automazioni (doc_events) ─────────────────────────────────────────
def auto_thankyou(doc, method=None):
    try:
        _send(_case_of(doc), "Thanatos - Ringraziamento e presa in carico", doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "auto_thankyou")


def auto_mandate_signed(doc, method=None):
    """Agency Mandate on_update: alla firma (signed_on appena valorizzato) -> conferma."""
    try:
        if doc.get("signed_on") and doc.has_value_changed("signed_on"):
            _send(_case_of(doc), "Thanatos - Mandato firmato", doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "auto_mandate_signed")


def auto_report_ready(doc, method=None):
    """Investigation Report after_insert -> notifica report pronto."""
    try:
        _send(_case_of(doc), "Thanatos - Report pronto", doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "auto_report_ready")
