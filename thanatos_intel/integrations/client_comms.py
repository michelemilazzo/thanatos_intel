"""Comunicazioni al cliente — dentro Thanatos Intel.

Invia Email Template al cliente di un Investigation Case, collegando la mail
al caso (compare nella timeline Comunicazioni di Thanatos). Supporta sia l'invio
manuale (bottone sul caso) sia l'automazione (auto-ringraziamento su nuovo caso).

I template sono Email Template con prefisso "Thanatos -".
"""
import frappe
from frappe import _

SENDER = "admin@thanatos.agency"


def _client_of(case_doc):
    """Ritorna (email, nome) del cliente del caso, o (None, None)."""
    client = case_doc.get("client")
    if not client:
        return None, None
    email = frappe.db.get_value("Investigation Client", client, "email")
    name = frappe.db.get_value("Investigation Client", client, "client_name") or client
    return email, name


@frappe.whitelist()
def list_templates():
    return frappe.get_all("Email Template", filters={"name": ["like", "Thanatos -%"]}, pluck="name")


@frappe.whitelist()
def send_to_client(case, template):
    """Invia un Email Template al cliente del caso, collegato al caso."""
    c = frappe.get_doc("Investigation Case", case)
    email, name = _client_of(c)
    if not email:
        frappe.throw(_("Il caso non ha un cliente con email. Collega un Investigation Client con email."))
    tpl = frappe.get_doc("Email Template", template)
    ctx = {"client_name": name, "case": c, "doc": c}
    subject = frappe.render_template(tpl.subject or "", ctx)
    body = frappe.render_template(tpl.response_html or tpl.response or "", ctx)
    frappe.sendmail(
        recipients=[email], sender=SENDER, subject=subject, message=body,
        reference_doctype="Investigation Case", reference_name=case,
    )
    return {"ok": True, "to": email, "template": template}


def auto_thankyou(doc, method=None):
    """doc_event after_insert su Investigation Case: ringraziamento + presa in carico
    al cliente, una sola volta, best-effort (non blocca la creazione del caso)."""
    try:
        TPL = "Thanatos - Ringraziamento e presa in carico"
        if not frappe.db.exists("Email Template", TPL):
            return
        email, name = _client_of(doc)
        if not email:
            return
        tpl = frappe.get_doc("Email Template", TPL)
        ctx = {"client_name": name, "case": doc, "doc": doc}
        frappe.sendmail(
            recipients=[email], sender=SENDER,
            subject=frappe.render_template(tpl.subject or "", ctx),
            message=frappe.render_template(tpl.response_html or "", ctx),
            reference_doctype="Investigation Case", reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "auto_thankyou")
