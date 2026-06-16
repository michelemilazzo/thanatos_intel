"""Dispatcher notifiche del Motore Pratiche.

Separazione netta per evitare doppi-save dello stesso Investigation Case:
- append_activity(case_doc, ...) : aggiunge la riga al feed IN MEMORIA sul doc
  che possiede il chiamante (che poi salva UNA volta). Nessun save qui.
- channels(case_name, ...)       : invia sui canali esterni (email, whatsapp).
  Solo letture sul caso, nessuna scrittura sul doc.

Canali: EMAIL (frappe.sendmail) + WHATSAPP (waba esistente). Telegram/push: F4.
"""
import frappe
from frappe.utils import now_datetime


def append_activity(case_doc, message, activity_type="Report"):
    """Riga di feed/bacheca, in memoria sul doc del chiamante (no save)."""
    case_doc.append("case_activities", {
        "activity_date": now_datetime(),
        "activity_type": activity_type,
        "description": (message or "")[:140],
        "operator": frappe.session.user,
    })


def _client_contact(case_name):
    client = frappe.db.get_value("Investigation Case", case_name, "client")
    if not client:
        return None, None
    email, name = frappe.db.get_value(
        "Investigation Client", client, ["email", "client_name"]) or (None, None)
    return email, name


def _email_client(case_name, subject, message):
    email, name = _client_contact(case_name)
    if not email:
        return False
    try:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=f"<p>Gentile {name or 'Cliente'},</p><p>{message}</p>"
                    f"<p>Segua la pratica nel portale: "
                    f"<a href='{frappe.utils.get_url()}/portal/case/{case_name}'>{case_name}</a></p>"
                    f"<p>— Thanatos Intel</p>",
            reference_doctype="Investigation Case", reference_name=case_name,
        )
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.notify.email")
        return False


def _whatsapp_client(case_name, event):
    try:
        from thanatos_intel.integrations import waba_notifications as waba
    except Exception:
        return False
    fn = {
        "mandate_ready": getattr(waba, "notify_mandate_ready", None),
        "payment_request": getattr(waba, "notify_payment_request", None),
        "report_ready": getattr(waba, "notify_report_ready", None),
    }.get(event)
    if not fn:
        return False
    try:
        fn(case_name)
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.notify.whatsapp")
        return False


def channels(case_name, message, subject=None, event=None, client_visible=True):
    """Invia sui canali esterni (no scrittura sul caso)."""
    if not client_visible:
        return
    _email_client(case_name, subject or "Aggiornamento pratica Thanatos", message)
    if event:
        _whatsapp_client(case_name, event)
