"""Ingest messaggi WhatsApp → Intel Lead.

Supporta:
- Twilio WhatsApp webhook (POST form-encoded)
- Meta/WhatsApp Cloud API webhook (POST JSON)

Configurazione site_config.json:
  whatsapp_ingest_token   — token segreto di validazione (obbligatorio)
  whatsapp_provider       — "twilio" | "meta" (default: auto-detect)

Endpoint webhook da configurare sul provider:
  https://thanatos.onekeyco.com/api/method/thanatos_intel.ingest.whatsapp.webhook
"""
import frappe
from frappe.utils import now_datetime


def _check_token(token: str) -> bool:
    expected = frappe.conf.get("whatsapp_ingest_token")
    if not expected:
        frappe.log_error("whatsapp_ingest_token non configurato in site_config", "WhatsApp Ingest")
        return False
    return token == expected


def _create_lead(source_id: str, source_name: str, content: str,
                 media_url: str = "", provider: str = "WhatsApp") -> str:
    doc = frappe.get_doc({
        "doctype": "Intel Lead",
        "received_at": now_datetime(),
        "source_type": "WhatsApp",
        "source_identifier": source_id,
        "source_name": source_name or "",
        "content": content or "(nessun testo)",
        "media_url": media_url or "",
        "status": "Nuovo",
        "priority": "Media",
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.name


def _parse_twilio(data: dict) -> list[dict]:
    """Estrae messaggio(i) da payload Twilio WhatsApp."""
    from_number = data.get("From", "").replace("whatsapp:", "")
    profile_name = data.get("ProfileName", "")
    body = data.get("Body", "")
    media_url = data.get("MediaUrl0", "")
    return [{"source_id": from_number, "source_name": profile_name,
             "content": body, "media_url": media_url}]


def _parse_meta(data: dict) -> list[dict]:
    """Estrae messaggio(i) da payload Meta Cloud API."""
    results = []
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {c["wa_id"]: c.get("profile", {}).get("name", "")
                        for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                wa_id = msg.get("from", "")
                content = (
                    msg.get("text", {}).get("body", "")
                    or msg.get("caption", "")
                    or f"[{msg.get('type', 'media')}]"
                )
                media_url = ""
                for mtype in ("image", "video", "audio", "document"):
                    if mtype in msg:
                        media_url = msg[mtype].get("link", "") or msg[mtype].get("id", "")
                        break
                results.append({
                    "source_id": wa_id,
                    "source_name": contacts.get(wa_id, ""),
                    "content": content,
                    "media_url": media_url,
                })
    return results


@frappe.whitelist(allow_guest=True)
def webhook():
    """Endpoint webhook generico — auto-detect Twilio vs Meta."""
    req = frappe.request

    # Validazione token
    token = (
        req.args.get("token")
        or req.form.get("token", "")
        if req.content_type and "form" in req.content_type
        else req.args.get("token", "")
    )
    if not _check_token(token):
        frappe.response["http_status_code"] = 403
        return {"error": "unauthorized"}

    # Meta usa GET per la verifica iniziale del webhook (challenge)
    if req.method == "GET":
        challenge = req.args.get("hub.challenge")
        verify = req.args.get("hub.verify_token", "")
        if _check_token(verify) and challenge:
            frappe.response["type"] = "page"
            frappe.response["page_content"] = challenge
            return
        frappe.response["http_status_code"] = 403
        return {"error": "invalid verify_token"}

    content_type = req.content_type or ""
    if "json" in content_type:
        data = frappe.request.json or {}
        messages = _parse_meta(data)
    else:
        data = req.form.to_dict()
        messages = _parse_twilio(data)

    created = []
    for m in messages:
        if not m["content"] and not m["media_url"]:
            continue
        name = _create_lead(
            source_id=m["source_id"],
            source_name=m["source_name"],
            content=m["content"],
            media_url=m["media_url"],
        )
        created.append(name)

    return {"created": created, "count": len(created)}
