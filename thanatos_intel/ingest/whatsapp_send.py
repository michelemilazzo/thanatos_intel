"""Invio messaggi WhatsApp in uscita da Intel Lead.

Supporta Meta Cloud API e Twilio.
Logga ogni messaggio nella child table Intel Lead Message.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def send_reply(lead_name: str, message_text: str) -> dict:
    lead = frappe.get_doc("Intel Lead", lead_name)

    if lead.source_type != "WhatsApp":
        frappe.throw(_("Questo lead non è di tipo WhatsApp."))

    to_number = (lead.source_identifier or "").strip()
    if not to_number:
        frappe.throw(_("Numero destinatario mancante nel lead."))

    wa_number_name = lead.whatsapp_number
    if not wa_number_name:
        frappe.throw(_("Nessun numero WhatsApp configurato per questo lead."))

    wa_doc = frappe.get_doc("WhatsApp Number", wa_number_name)
    if not wa_doc.is_active:
        frappe.throw(_("Il numero WhatsApp {0} non è attivo.").format(wa_number_name))

    provider = wa_doc.provider or "Meta Cloud API"

    if provider == "Meta Cloud API":
        result = _send_via_meta(wa_doc, to_number, message_text)
    elif provider == "Twilio":
        result = _send_via_twilio(wa_doc, to_number, message_text)
    else:
        frappe.throw(_("Provider non supportato per l'invio: {0}").format(provider))

    # Log messaggio nella child table
    lead.append("messages", {
        "direction": "Outbound",
        "sent_at": now_datetime(),
        "content": message_text,
        "status": "Inviato" if result.get("ok") else "Fallito",
        "sent_by": frappe.session.user,
        "wa_message_id": result.get("message_id", ""),
    })
    lead.db_set("last_message_at", now_datetime(), notify=False)
    lead.save(ignore_permissions=True)
    frappe.db.commit()

    if not result.get("ok"):
        frappe.throw(_("Errore invio WA: {0}").format(result.get("error", "sconosciuto")))

    return {"ok": True, "message_id": result.get("message_id", "")}


def _send_via_meta(wa_doc, to_number: str, text: str) -> dict:
    phone_number_id = wa_doc.meta_phone_number_id
    access_token = frappe.utils.password.get_decrypted_password(
        "WhatsApp Number", wa_doc.name, "meta_access_token"
    )
    if not phone_number_id or not access_token:
        return {"ok": False, "error": "meta_phone_number_id o meta_access_token mancanti"}

    to_clean = to_number.lstrip("+").replace(" ", "").replace("-", "")

    import requests
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_clean,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    resp = requests.post(url, json=payload,
                         headers={"Authorization": f"Bearer {access_token}"},
                         timeout=15)
    data = resp.json()
    if resp.status_code == 200 and data.get("messages"):
        return {"ok": True, "message_id": data["messages"][0].get("id", "")}
    return {"ok": False, "error": data.get("error", {}).get("message", str(data))}


def _send_via_twilio(wa_doc, to_number: str, text: str) -> dict:
    account_sid = wa_doc.twilio_account_sid
    auth_token = frappe.utils.password.get_decrypted_password(
        "WhatsApp Number", wa_doc.name, "twilio_auth_token"
    )
    from_number = wa_doc.phone_number
    if not account_sid or not auth_token or not from_number:
        return {"ok": False, "error": "Credenziali Twilio mancanti"}

    import requests
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    resp = requests.post(url,
                         data={
                             "From": f"whatsapp:{from_number}",
                             "To": f"whatsapp:{to_number}",
                             "Body": text,
                         },
                         auth=(account_sid, auth_token),
                         timeout=15)
    data = resp.json()
    if resp.status_code in (200, 201) and data.get("sid"):
        return {"ok": True, "message_id": data["sid"]}
    return {"ok": False, "error": data.get("message", str(data))}


@frappe.whitelist()
def reassign_lead(lead_name: str, new_user: str, note: str = "") -> dict:
    lead = frappe.get_doc("Intel Lead", lead_name)
    old_user = lead.assigned_to

    lead.db_set("assigned_to", new_user, notify=True)
    frappe.db.commit()

    # Notifica operatore ricevente
    try:
        from thanatos_intel.ingest.intel_notifications import notify_transferred
        notify_transferred(lead_name, new_user, frappe.session.user)
    except Exception:
        pass

    # Aggiungi nota interna se fornita
    if note:
        lead.reload()
        lead.append("messages", {
            "direction": "Outbound",
            "sent_at": now_datetime(),
            "content": f"[Trasferito da {frappe.session.user} a {new_user}] {note}",
            "status": "Inviato",
            "sent_by": frappe.session.user,
        })
        lead.save(ignore_permissions=True)
        frappe.db.commit()

    return {"ok": True, "old": old_user, "new": new_user}
