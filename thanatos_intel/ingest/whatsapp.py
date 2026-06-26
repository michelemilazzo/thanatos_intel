"""Ingest messaggi WhatsApp → Intel Lead.

Supporta multi-numero tramite DocType WhatsApp Number.
Ogni numero ha il proprio token e configurazione provider.

Webhook URL (da impostare su Twilio/Meta):
  https://thanatos.agency/api/method/thanatos_intel.ingest.whatsapp.webhook
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
                    "wa_message_id": msg.get("id", ""),
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

    # Gestisce eventi di monitoraggio account (template/qualità/account/alert)
    if "json" in (req.content_type or "") and _has_account_events(data):
        _handle_account_events(data)
        return {"ok": True, "type": "account_event"}

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

        # Risposta automatica: bot AI se abilitato sul numero, altrimenti messaggio fisso
        try:
            from frappe.utils import add_to_date, now_datetime
            bot_on = bool(
                wa_number and frappe.db.get_value(
                    'WhatsApp Number', wa_number.get('phone_number'), 'ai_bot_enabled')
            )
            txt = (m.get('content') or '').strip()
            if bot_on and txt and not txt.startswith('['):
                _mark_read_typing(wa_number.get('phone_number'), m.get('wa_message_id'))
                frappe.enqueue(
                    'thanatos_intel.ingest.wa_bot.generate_reply',
                    queue='short', timeout=200,
                    lead_name=name, wa_number=wa_number.get('phone_number'),
                    to_number=m['source_id'],
                )
            else:
                cutoff = add_to_date(now_datetime(), hours=-4)
                recent_outbound = frappe.db.count('Intel Lead Message', {
                    'parent': name, 'direction': 'Outbound', 'sent_at': ['>=', cutoff]
                })
                if not recent_outbound:
                    _send_auto_reply(wa_number, m['source_id'], name, is_new=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), 'WA auto-reply dispatch')

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




def _mark_read_typing(phone_number, wamid):
    """Marca il messaggio come letto e mostra l'indicatore 'sta scrivendo...'
    al cliente, per ridurre il lag percepito mentre il bot genera la risposta."""
    if not (phone_number and wamid):
        return
    pnid = frappe.db.get_value("WhatsApp Number", phone_number, "meta_phone_number_id")
    if not pnid:
        return
    from frappe.utils.password import get_decrypted_password
    token = get_decrypted_password("WhatsApp Number", phone_number, "meta_access_token")
    if not token:
        return
    try:
        import requests as _r
        _r.post(f"https://graph.facebook.com/v21.0/{pnid}/messages",
                json={"messaging_product": "whatsapp", "status": "read",
                      "message_id": wamid, "typing_indicator": {"type": "text"}},
                headers={"Authorization": f"Bearer {token}"}, timeout=8)
    except Exception:
        pass


def _send_auto_reply(wa_number, to_number: str, lead_name: str, is_new: bool):
    # Invia auto-reply se configurato. Non richiede frappe.session.
    if not wa_number:
        return
    wa_doc_name = wa_number.get('phone_number') if isinstance(wa_number, dict) else wa_number
    if not wa_doc_name:
        return
    try:
        wa_doc = frappe.get_doc('WhatsApp Number', wa_doc_name)
    except Exception:
        return
    msg = (wa_doc.auto_reply_message or '').strip()
    if not msg:
        return
    if not is_new and not wa_doc.auto_reply_always:
        return
    fwd = (wa_doc.call_forward_number or '').strip()
    if fwd:
        msg = msg.replace('{numero_operatore}', fwd)
    else:
        msg = msg.replace(' {numero_operatore}', '').replace('{numero_operatore}', '')
    from frappe.utils.password import get_decrypted_password
    phone_number_id = wa_doc.meta_phone_number_id
    access_token = get_decrypted_password('WhatsApp Number', wa_doc.name, 'meta_access_token')
    if not phone_number_id or not access_token:
        return
    to_clean = to_number.lstrip('+').replace(' ', '').replace('-', '')
    try:
        import requests as _req
        resp = _req.post(
            f'https://graph.facebook.com/v21.0/{phone_number_id}/messages',
            json={'messaging_product': 'whatsapp', 'recipient_type': 'individual',
                  'to': to_clean, 'type': 'text', 'text': {'preview_url': False, 'body': msg}},
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=15,
        )
        data = resp.json()
        ok = resp.status_code == 200 and data.get('messages')
        mid = data['messages'][0].get('id', '') if ok else ''
        from frappe.utils import now_datetime
        lead = frappe.get_doc('Intel Lead', lead_name)
        lead.append('messages', {
            'direction': 'Outbound',
            'sent_at': now_datetime(),
            'content': msg,
            'status': 'Inviato' if ok else 'Fallito',
            'sent_by': 'Administrator',
            'wa_message_id': mid,
        })
        lead.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), 'WA auto-reply')
def _has_call_events(data: dict) -> bool:
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "calls" or change.get("value", {}).get("calls"):
                return True
    return False


def _handle_call_events(data: dict, wa_number: dict | None):
    """Eventi chiamata WhatsApp. Su 'connect' inoltra l'SDP al media server (aiortc)
    che accetta la chiamata, registra l'audio e a fine chiamata crea il Call Log
    con trascrizione+voci. Notifica l'operatore (chiamata in arrivo)."""
    from thanatos_intel.ingest.intel_notifications import _notify
    from thanatos_intel.ingest.contacts import ensure_contact_from_wa
    for entry in data.get("entry", []):
        pnid = entry.get("changes", [{}])[0].get("value", {}).get(
            "metadata", {}).get("phone_number_id", "")
        for change in entry.get("changes", []):
            val = change.get("value", {})
            pnid = val.get("metadata", {}).get("phone_number_id", pnid)
            # nome profilo WhatsApp del chiamante (dai contacts)
            profiles = {c.get("wa_id", ""): c.get("profile", {}).get("name", "")
                        for c in val.get("contacts", [])}
            for call in val.get("calls", []):
                frm = call.get("from", "")
                event = call.get("event", "") or call.get("status", "")
                call_id = call.get("id", "")
                # crea/arricchisce la scheda contatto col nome profilo
                if event == "connect":
                    try:
                        ensure_contact_from_wa(frm, profiles.get(frm, ""), "Chiamata WhatsApp")
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), "ensure contact call")
                session = call.get("session", {}) or {}
                sdp = session.get("sdp", "")

                # CONNECT con SDP: prima verifica se è la gamba operatore che risponde
                if event == "connect" and sdp:
                    try:
                        from thanatos_intel.api.wa_calling import operator_answer as _op_ans
                        if _op_ans(call_id, sdp):
                            continue  # operatore agganciato → bridge attivo
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), "WA operator_answer")
                    if not pnid:
                        continue
                    # gamba cliente: accetta sul media server (registra + dirotta all'operatore)
                    try:
                        from thanatos_intel.api.wa_calling import forward_incoming_call
                        res = forward_incoming_call(call_id, pnid, frm, sdp, wa_number)
                        frappe.log_error(frappe.as_json(res)[:500], "WA call accept")
                    except Exception:
                        frappe.log_error(frappe.get_traceback(), "WA call forward")
                    try:
                        from thanatos_intel.api.wa_calling import _resolve_caller
                        caller = _resolve_caller(frm)
                    except Exception:
                        caller = {}
                    who = caller.get("name") or "Sconosciuto"
                    org = (" · " + caller["org"]) if caller.get("org") else ""
                    assigned = caller.get("assigned_name") or ""
                    assignee = caller.get("assigned_to") or (wa_number.auto_assign_to if wa_number else None) or "Administrator"
                    ref = caller.get("lead") or ""
                    msg = (f"Da: <b>{who}</b>{org}<br>Numero: {frm}"
                           + (f"<br>Assegnato a: {assigned}" if assigned else "")
                           + "<br>In dirottamento all'operatore")
                    try:
                        frappe.publish_realtime("centralino_incoming_call",
                                                {"call_id": call_id, "from": frm, "caller": caller}, after_commit=False)
                        _notify(assignee, "📞 Chiamata WhatsApp in arrivo",
                                msg, ref, "blue")
                    except Exception:
                        pass
                    continue

                # terminate/reject → chiudi sessione media + log
                if event in ("terminate", "reject"):
                    try:
                        import requests
                        requests.post(f"{frappe.conf.get('wa_calling_url','http://10.10.0.4:18093')}/terminate",
                                      json={"call_id": call_id}, timeout=10)
                    except Exception:
                        pass


_MONITOR_FIELDS = {
    "message_template_status_update", "phone_number_quality_update",
    "account_update", "account_alerts", "account_review_update",
    "business_capability_update",
}


def _has_account_events(data: dict) -> bool:
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") in _MONITOR_FIELDS:
                return True
    return False


def _monitor_recipients() -> list[str]:
    """Utenti da avvisare per eventi di monitoraggio account."""
    users = frappe.db.sql_list(
        """SELECT DISTINCT u.name FROM `tabUser` u
           JOIN `tabHas Role` r ON r.parent = u.name
           WHERE r.role IN ('Investigation Manager','System Manager')
             AND u.enabled = 1 AND u.name NOT IN ('Guest','Administrator')""")
    return users or ["Administrator"]


def _handle_account_events(data: dict):
    """Notifica gli admin per eventi di salute account (template, qualità numero, restrizioni)."""
    from thanatos_intel.ingest.intel_notifications import _notify
    recipients = _monitor_recipients()

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field")
            if field not in _MONITOR_FIELDS:
                continue
            v = change.get("value", {})
            title, msg, indicator = _format_account_event(field, v)
            if not title:
                continue
            for user in recipients:
                try:
                    _notify(user, title, msg, None, indicator)
                except Exception:
                    pass
            frappe.log_error(f"{field}: {frappe.as_json(v)[:1500]}", f"WA monitor {field}")
    frappe.db.commit()


def _format_account_event(field: str, v: dict) -> tuple:
    ev = v.get("event", "")
    if field == "message_template_status_update":
        name = v.get("message_template_name", "")
        if ev == "APPROVED":
            return ("✅ Template approvato", f"Il template '{name}' è stato approvato da Meta.", "green")
        if ev in ("REJECTED", "DISABLED", "PAUSED"):
            reason = v.get("reason", "")
            return (f"⛔ Template {ev.lower()}", f"Template '{name}': {ev}. {reason}", "red")
        return (f"ℹ️ Template aggiornato", f"Template '{name}': {ev}", "blue")
    if field == "phone_number_quality_update":
        if ev in ("FLAGGED", "DOWNGRADE"):
            return ("⚠️ Qualità numero in calo",
                    f"La qualità del numero WhatsApp è scesa ({ev}, limite {v.get('current_limit','')}). Rischio limitazioni.", "red")
        return ("📈 Qualità numero aggiornata", f"Stato qualità numero: {ev} (limite {v.get('current_limit','')})", "blue")
    if field in ("account_update", "account_review_update"):
        return ("🔔 Aggiornamento account WhatsApp", f"Evento account: {ev or v}", "orange")
    if field == "account_alerts":
        sev = v.get("alert_severity", "")
        desc = v.get("alert_description", v.get("alert_type", ""))
        return (f"🚨 Avviso account WhatsApp ({sev})", desc or "Avviso da Meta sull'account.", "red")
    if field == "business_capability_update":
        return ("📊 Limiti account aggiornati", f"Capacità/limiti cambiati: {v}", "blue")
    return (None, None, None)


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
