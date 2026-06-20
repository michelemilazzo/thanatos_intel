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
    case_url = f"{frappe.utils.get_url()}/portal/case/{case_name}"
    # Bulletproof button (table+bgcolor): Outlook ignora il padding sui link <a>,
    # quindi il bottone va costruito su una cella di tabella con bgcolor.
    cta = (
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' "
        "style='margin:6px 0 20px'><tr>"
        f"<td bgcolor='#C8A96E' style='border-radius:4px'>"
        f"<a href='{url}' style='display:inline-block;padding:13px 26px;"
        "font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;"
        f"color:#0A0E1A;text-decoration:none;border-radius:4px'>{label} &rsaquo;</a>"
        "</td></tr></table>"
    )
    # Corpo fluido table-based (Outlook usa il motore Word: niente max-width su div).
    body = (
        "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' border='0'>"
        "<tr><td style='font-family:Arial,Helvetica,sans-serif;font-size:15px;"
        "line-height:1.6;color:#222'>"
        f"<p style='margin:0 0 12px'>Gentile {name or 'Cliente'},</p>"
        f"<p style='margin:0 0 4px'>{message}</p>"
        f"{cta}"
        "<p style='margin:0;font-size:12px;color:#777'>Oppure apri la pratica: "
        f"<a href='{case_url}' style='color:#C8A96E'>{case_name}</a></p>"
        "</td></tr></table>"
    )
    try:
        frappe.sendmail(
            recipients=[email],
            subject=subject,
            message=body,
            reference_doctype="Investigation Case", reference_name=case_name,
            # Reply-to dedicato SOLO alle notifiche di pratica: le risposte del
            # cliente arrivano a cases@ → ingest inbound (link al caso + box/Vault).
            reply_to="cases@thanatos.agency",
            # container = logo Thanatos in intestazione (brand_logo dell'account).
            with_container=True,
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


def _email_operator(case_name, subject, message, from_user=None):
    """Notifica email all'investigatore/manager assegnato al caso.
    Fallback a admin@thanatos.agency se non c'è assegnatario."""
    try:
        assignee = frappe.db.get_value("Investigation Case", case_name, "assigned_to")
        if assignee:
            op_email = frappe.db.get_value("User", assignee, "email") or assignee
        else:
            op_email = "admin@thanatos.agency"
        case_url = f"{frappe.utils.get_url()}/app/investigation-case/{case_name}"
        body = (
            f"<p>Messaggio ricevuto per la pratica "
            f"<a href='{case_url}'>{case_name}</a>:</p>"
            f"<blockquote style='border-left:3px solid #C8A96E;margin:8px 0;padding:8px 16px;"
            f"color:#444;background:#fafafa'>{message}</blockquote>"
            + (f"<p style='font-size:12px;color:#777'>Da: {from_user}</p>" if from_user else "")
        )
        frappe.sendmail(
            recipients=[op_email], subject=subject,
            message=body,
            reference_doctype="Investigation Case", reference_name=case_name,
            now=False,
        )
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "workflow.notify.email_operator")
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
