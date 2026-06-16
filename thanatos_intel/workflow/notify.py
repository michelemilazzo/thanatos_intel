"""Dispatcher notifiche unico del Motore Pratiche.

Aggrega i canali esistenti. Ogni evento del caso passa di qui:
- BACHECA: sempre (riga Case Activity = feed + audit).
- EMAIL: al cliente se l'evento e' client-visible (riusa frappe.sendmail).
- WHATSAPP: best-effort via integrations.waba_notifications (gia' esistente).
- TELEGRAM / PUSH: stub (loggati), da implementare in F4.

Canali pluggabili: estendere CHANNELS. Le preferenze per-cliente arriveranno
da Investigation Client (campo notify_channels), per ora email+bacheca sempre.
"""
import frappe
from frappe.utils import now_datetime


def _client_contact(case_name):
    client = frappe.db.get_value("Investigation Case", case_name, "client")
    if not client:
        return None, None, None
    email, name, phone = frappe.db.get_value(
        "Investigation Client", client, ["email", "client_name", "phone"]
    ) or (None, None, None)
    return email, name, phone


def log_activity(case_name, message, activity_type="Report"):
    """Scrive una riga nel feed del caso (bacheca + audit)."""
    try:
        case = frappe.get_doc("Investigation Case", case_name)
        case.append("case_activities", {
            "activity_date": now_datetime(),
            "activity_type": activity_type,
            "description": message[:140],
            "operator": frappe.session.user,
        })
        case.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.notify.log_activity")


def _email_client(case_name, subject, message):
    email, name, _phone = _client_contact(case_name)
    if not email:
        return False
    try:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=f"<p>Gentile {name or 'Cliente'},</p><p>{message}</p>"
                    f"<p>Pu&ograve; seguire la pratica nel portale: "
                    f"<a href='{frappe.utils.get_url()}/portal/case/{case_name}'>{case_name}</a></p>"
                    f"<p>— Thanatos Intel</p>",
            reference_doctype="Investigation Case",
            reference_name=case_name,
        )
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.notify.email")
        return False


def _whatsapp_client(case_name, event):
    """Best-effort: mappa l'evento ai template WABA esistenti dove disponibili."""
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


def dispatch(case_name, message, subject=None, event=None, client_visible=True,
             activity_type="Report"):
    """Punto unico: logga in bacheca e instrada sui canali."""
    log_activity(case_name, message, activity_type=activity_type)
    if client_visible:
        _email_client(case_name, subject or "Aggiornamento pratica Thanatos", message)
        if event:
            _whatsapp_client(case_name, event)
    # telegram / push: F4
    return True
