"""Invio messaggi diretti Instagram in uscita da Intel Lead.

Gemello di ``whatsapp_send.py`` per il canale Instagram (Meta Messaging API).
Logga ogni messaggio nella child table Intel Lead Message.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime


def _post_message(account: str, to_id: str, payload: dict) -> dict:
    """POST del messaggio su Graph. Prova l'endpoint IG, poi la Page collegata.

    Meta espone il DM sia su ``/{ig_user_id}/messages`` (Instagram Login) sia su
    ``/{page_id}/messages`` (Facebook Login for Business): quale dei due risponda
    dipende da come l'app e' stata collegata, quindi li proviamo in cascata.
    """
    import requests
    from thanatos_intel.ingest.instagram import GRAPH, account_token

    acc = frappe.db.get_value("Instagram Account", account,
                              ["ig_user_id", "page_id"], as_dict=True)
    if not acc:
        return {"ok": False, "error": f"Instagram Account {account} inesistente"}
    token = account_token(account)
    if not token:
        return {"ok": False, "error": "Access token mancante sull'Instagram Account"}

    body = {"recipient": {"id": to_id}, **payload}
    last_err = ""
    for node in [n for n in (acc.ig_user_id, acc.page_id) if n]:
        try:
            r = requests.post(f"{GRAPH}/{node}/messages", json=body,
                              headers={"Authorization": f"Bearer {token}"}, timeout=20)
            data = r.json()
        except Exception as e:
            last_err = str(e)
            continue
        if r.status_code == 200 and not data.get("error"):
            return {"ok": True, "message_id": data.get("message_id", "")}
        last_err = (data.get("error") or {}).get("message", str(data))
    return {"ok": False, "error": last_err or "invio fallito"}


def send_dm(account: str, to_id: str, text: str, lead_name: str | None = None,
            sent_by: str = "Administrator") -> dict:
    """Invia un DM e (se lead_name) logga il messaggio nel thread."""
    result = _post_message(account, to_id, {"message": {"text": text}})

    if lead_name:
        try:
            lead = frappe.get_doc("Intel Lead", lead_name)
            lead.append("messages", {
                "direction": "Outbound",
                "sent_at": now_datetime(),
                "content": text,
                "status": "Inviato" if result.get("ok") else "Fallito",
                "sent_by": sent_by,
                "wa_message_id": result.get("message_id", ""),
            })
            lead.db_set("last_message_at", now_datetime(), notify=False)
            lead.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "IG send_dm log")

    if not result.get("ok"):
        frappe.log_error(result.get("error", ""), "IG send_dm")
    return result


@frappe.whitelist()
def send_reply(lead_name: str, message_text: str) -> dict:
    """Risposta operatore dal Centralino verso un lead Instagram."""
    lead = frappe.get_doc("Intel Lead", lead_name)
    if lead.source_type != "Instagram":
        frappe.throw(_("Questo lead non è di tipo Instagram."))

    to_id = (lead.source_identifier or "").strip()
    if not to_id:
        frappe.throw(_("Destinatario Instagram mancante nel lead."))

    account = lead.instagram_account
    if not account:
        frappe.throw(_("Nessun account Instagram configurato per questo lead."))
    if not frappe.db.get_value("Instagram Account", account, "is_active"):
        frappe.throw(_("L'account Instagram {0} non è attivo.").format(account))

    result = send_dm(account, to_id, message_text, lead_name,
                     sent_by=frappe.session.user)
    if not result.get("ok"):
        frappe.throw(_("Errore invio Instagram: {0}").format(
            result.get("error", "sconosciuto")))
    return {"ok": True, "message_id": result.get("message_id", "")}
