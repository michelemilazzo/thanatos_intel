"""Ingest messaggi WhatsApp → Intel Lead.

Supporta multi-numero tramite DocType WhatsApp Number.
Ogni numero ha il proprio token e configurazione provider.

Webhook URL (da impostare su Twilio/Meta):
  https://thanatos.onekeyco.com/api/method/thanatos_intel.ingest.whatsapp.webhook
  ?number_id=+39123456789&token=IL-TUO-TOKEN

  oppure (fallback globale):
  ?token=IL-TUO-TOKEN-GLOBALE  (usa whatsapp_ingest_token in site_config)

Configurazione site_config.json (fallback globale):
  whatsapp_ingest_token   — token globale quando number_id non specificato
"""
import frappe
from frappe.utils.password import get_decrypted_password


def _load_number(number_id: str) -> dict | None:
    """Carica config WhatsApp Number da DB."""
    if not number_id:
        return None
    rec = frappe.db.get_value(
        "WhatsApp Number",
        number_id,
        ["display_name", "phone_number", "provider", "webhook_token",
         "auto_assign_to", "default_priority", "default_tags", "is_active"],
        as_dict=True,
    )
    return rec if rec and rec.is_active else None


def _check_token(token: str, wa_number: dict | None) -> bool:
    """Valida il token: prima controlla il numero specifico, poi il token globale."""
    if wa_number:
        expected = get_decrypted_password(
            "WhatsApp Number", wa_number.phone_number, "webhook_token"
        ) if wa_number.webhook_token else None
        if expected:
            return token == expected
    # fallback globale
    global_token = frappe.conf.get("whatsapp_ingest_token")
    return bool(global_token and token == global_token)


def _create_lead(source_id: str, source_name: str, content: str,
                 media_url: str = "", wa_number: dict | None = None) -> str:
    from thanatos_intel.thanatos_core.doctype.intel_lead.intel_lead import find_or_create_lead
    return find_or_create_lead(
        source_identifier=source_id,
        source_name=source_name,
        content=content,
        source_type="WhatsApp",
        media_url=media_url,
        wa_number=wa_number,
    )


def _parse_twilio(data: dict) -> list[dict]:
    from_number = data.get("From", "").replace("whatsapp:", "")
    profile_name = data.get("ProfileName", "")
    body = data.get("Body", "")
    media_url = data.get("MediaUrl0", "")
    return [{"source_id": from_number, "source_name": profile_name,
             "content": body, "media_url": media_url}]


def _parse_meta(data: dict) -> list[dict]:
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
                media_type = ""
                media_id = ""
                media_filename = ""
                for mtype in ("image", "video", "audio", "document"):
                    if mtype in msg:
                        media_type = mtype
                        media_id = msg[mtype].get("id", "")
                        media_url = msg[mtype].get("link", "") or media_id
                        media_filename = msg[mtype].get("filename", "")
                        break
                results.append({
                    "source_id": wa_id,
                    "source_name": contacts.get(wa_id, ""),
                    "content": content,
                    "media_url": media_url,
                    "media_type": media_type,
                    "media_id": media_id,
                    "media_filename": media_filename,
                })
    return results


@frappe.whitelist(allow_guest=True)
def webhook():
    """Endpoint webhook multi-numero — auto-detect Twilio vs Meta."""
    req = frappe.request
    args = req.args

    number_id = args.get("number_id", "").strip()
    token = args.get("token", "").strip()

    # Carica numero specifico se fornito
    wa_number = _load_number(number_id) if number_id else None

    # Verifica challenge Meta (GET)
    if req.method == "GET":
        from werkzeug.wrappers import Response
        challenge = args.get("hub.challenge")
        verify = args.get("hub.verify_token", "")
        if _check_token(verify, wa_number) and challenge:
            return Response(challenge, status=200, content_type="text/plain")
        return Response("invalid verify_token", status=403, content_type="text/plain")

    if not _check_token(token, wa_number):
        frappe.response["http_status_code"] = 403
        return {"error": "unauthorized"}

    content_type = req.content_type or ""
    if "json" in content_type:
        data = req.json or {}
        if frappe.conf.get("whatsapp_debug_payload"):
            try:
                frappe.log_error(frappe.as_json(data)[:4000], "WA raw payload")
            except Exception:
                pass
        # Auto-detect numero Meta dal phone_number_id nel payload
        if not wa_number:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    pid = change.get("value", {}).get("metadata", {}).get("phone_number_id")
                    if pid:
                        rec = frappe.db.get_value(
                            "WhatsApp Number", {"meta_phone_number_id": pid, "is_active": 1},
                            ["display_name", "phone_number", "provider", "webhook_token",
                             "auto_assign_to", "default_priority", "default_tags", "is_active"],
                            as_dict=True,
                        )
                        if rec:
                            wa_number = rec
                        break
                if wa_number:
                    break
        messages = _parse_meta(data)
    else:
        data = req.form.to_dict()
        # Auto-detect numero Twilio dal To field
        if not wa_number:
            to_field = data.get("To", "").replace("whatsapp:", "")
            if to_field:
                rec = frappe.db.get_value(
                    "WhatsApp Number", {"phone_number": to_field, "is_active": 1},
                    ["display_name", "phone_number", "provider", "webhook_token",
                     "auto_assign_to", "default_priority", "default_tags", "is_active"],
                    as_dict=True,
                )
                if rec:
                    wa_number = rec
        messages = _parse_twilio(data)

    # Gestisce eventi chiamata WhatsApp (field "calls")
    if "json" in (req.content_type or "") and _has_call_events(data):
        _handle_call_events(data, wa_number)
        return {"ok": True, "type": "call_event"}

    # Gestisce status update (Meta: statuses array invece di messages)
    if "json" in (req.content_type or "") and not messages:
        _handle_status_updates(data)
        return {"ok": True, "type": "status_update"}

    created = []
    for m in messages:
        if not m["content"] and not m["media_url"]:
            continue
        name = _create_lead(
            source_id=m["source_id"],
            source_name=m["source_name"],
            content=m["content"],
            media_url=m["media_url"],
            wa_number=wa_number,
        )
        created.append(name)

        # Media in arrivo → scarica + allega (audio anche trascritto)
        if m.get("media_id"):
            _wa_phone = wa_number.phone_number if wa_number else None
            if m.get("media_type") == "audio":
                frappe.enqueue(
                    "thanatos_intel.ingest.voice_notes.process_voice_note",
                    queue="long", timeout=600,
                    lead_name=name, media_id=m["media_id"], wa_phone=_wa_phone,
                )
            elif m.get("media_type") in ("image", "video", "document"):
                frappe.enqueue(
                    "thanatos_intel.ingest.voice_notes.process_media_attachment",
                    queue="long", timeout=600,
                    lead_name=name, media_id=m["media_id"],
                    media_type=m["media_type"], filename=m.get("media_filename", ""),
                    wa_phone=_wa_phone,
                )

    return {"created": created, "count": len(created)}


def _has_call_events(data: dict) -> bool:
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "calls" or change.get("value", {}).get("calls"):
                return True
    return False


def _handle_call_events(data: dict, wa_number: dict | None):
    """Riceve gli eventi chiamata WhatsApp → crea Call Log + notifica operatore.

    NB: l'audio della chiamata richiede un media server WebRTC (non gestito qui).
    Questo handler registra l'evento (chiamata persa/ricevuta) per tracciabilità.
    """
    from thanatos_intel.ingest.intel_notifications import _notify
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for call in change.get("value", {}).get("calls", []):
                frm = call.get("from", "")
                status = call.get("event", "") or call.get("status", "")
                call_id = call.get("id", "")
                contact = frappe.db.get_value(
                    "Intelligence Contact", {"phone": frm}, "name") or \
                    frappe.db.get_value("Intelligence Contact", {"whatsapp": frm}, "name")
                try:
                    doc = frappe.get_doc({
                        "doctype": "Call Log",
                        "called_at": frappe.utils.now_datetime(),
                        "direction": "Entrante",
                        "outcome": "Risposta" if status in ("connect", "connected", "accepted") else "Non risposto",
                        "caller_number": frm,
                        "linked_contact": contact,
                        "summary": f"Chiamata WhatsApp ({status}) · id {call_id}",
                    }).insert(ignore_permissions=True)
                    frappe.db.commit()
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "WA call event")
                    continue
                assignee = (wa_number.auto_assign_to if wa_number else None) or "Administrator"
                try:
                    _notify(assignee, "📞 Chiamata WhatsApp",
                            f"Chiamata da {frm} ({status})", doc.name, "blue")
                except Exception:
                    pass


def _handle_status_updates(data: dict):
    """Aggiorna stato (consegnato/letto) dei messaggi outbound."""
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for st in change.get("value", {}).get("statuses", []):
                wa_msg_id = st.get("id")
                new_status = {"sent": "Inviato", "delivered": "Consegnato",
                              "read": "Letto", "failed": "Fallito"}.get(st.get("status"), "")
                if not wa_msg_id or not new_status:
                    continue
                # Cerca nella child table
                row = frappe.db.get_value(
                    "Intel Lead Message",
                    {"wa_message_id": wa_msg_id},
                    ["name", "parent"],
                    as_dict=True,
                )
                if row:
                    frappe.db.set_value("Intel Lead Message", row.name, "status", new_status)
                    try:
                        frappe.publish_realtime(
                            "centralino_update",
                            {"lead": row.parent, "type": "status",
                             "wa_message_id": wa_msg_id, "status": new_status},
                            after_commit=True,
                        )
                    except Exception:
                        pass
    frappe.db.commit()
