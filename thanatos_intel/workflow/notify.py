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


def action_link(case_name, action_type):
    """URL azionabile per lo step corrente (link che il cliente deve cliccare)."""
    base = frappe.utils.get_url()
    m = {
        "sign": (f"{base}/portal/case/{case_name}", "Firma il mandato"),
        "pay": (f"{base}/portal/billing", "Vai al pagamento"),
        "upload": (f"{base}/portal/upload?case={case_name}", "Carica i documenti"),
        "ai_question": (f"{base}/portal/case/{case_name}", "Rispondi nella pratica"),
        "deliver": (f"{base}/portal/case/{case_name}", "Scarica il report"),
    }
    return m.get(action_type, (f"{base}/portal/case/{case_name}", "Apri la pratica"))


def _email_client(case_name, subject, message, action_type=None):
    email, name = _client_contact(case_name)
    if not email:
        return False
    url, label = action_link(case_name, action_type)
    cta = (f"<p style='margin:18px 0'><a href='{url}' "
           f"style='background:#C8A96E;color:#0A0E1A;padding:10px 20px;border-radius:4px;"
           f"text-decoration:none;font-weight:bold'>{label} &rsaquo;</a></p>")
    try:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=f"<p>Gentile {name or 'Cliente'},</p><p>{message}</p>{cta}"
                    f"<p style='font-size:12px;color:#777'>Oppure apri la pratica: "
                    f"<a href='{frappe.utils.get_url()}/portal/case/{case_name}'>{case_name}</a></p>"
                    f"<p>— Thanatos Intel</p>",
            reference_doctype="Investigation Case", reference_name=case_name,
            # Reply-to dedicato SOLO alle notifiche di pratica: le risposte del
            # cliente arrivano a cases@ → ingest inbound (link al caso + box/Vault).
            reply_to="cases@thanatos.agency",
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


def channels(case_name, message, subject=None, event=None, client_visible=True, action_type=None):
    """Invia sui canali esterni (no scrittura sul caso): email con link
    azionabile + whatsapp + telegram (vedi telegram_channel)."""
    if not client_visible:
        return
    _email_client(case_name, subject or "Aggiornamento pratica Thanatos", message, action_type=action_type)
    if event:
        _whatsapp_client(case_name, event)
    try:
        from thanatos_intel.integrations.telegram_channel import notify_telegram
        url, label = action_link(case_name, action_type)
        notify_telegram(case_name, f"{message}\n{label}: {url}")
    except Exception:
        pass
