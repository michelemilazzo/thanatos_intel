"""Invio messaggi WhatsApp in uscita da Intel Lead.

Supporta Meta Cloud API e Twilio.
Logga ogni messaggio nella child table Intel Lead Message.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password


@frappe.whitelist()
def send_reply(lead_name: str, message_text: str) -> dict:
    lead = frappe.get_doc("Intel Lead", lead_name)

    # il Centralino usa un endpoint solo per tutti i canali: instrada su Instagram
    if lead.source_type == "Instagram":
        from thanatos_intel.ingest.instagram_send import send_reply as ig_send_reply
        return ig_send_reply(lead_name, message_text)

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
    access_token = get_decrypted_password(
        "WhatsApp Number", wa_doc.name, "meta_access_token"
    )
    if not phone_number_id or not access_token:
        return {"ok": False, "error": "meta_phone_number_id o meta_access_token mancanti"}

    to_clean = to_number.lstrip("+").replace(" ", "").replace("-", "")

    import requests
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
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


# stato Meta -> nostro is_active: solo APPROVED e' inviabile.
_TEMPLATE_ACTIVE_STATUSES = {"APPROVED"}


@frappe.whitelist()
def sync_template_status(whatsapp_number: str | None = None) -> dict:
    """Allinea lo stato dei WhatsApp Template col loro stato reale su Meta, così
    non serve controllare a mano dopo aver sottoposto un template ad approvazione.
    is_active = 1 solo se APPROVED; salva anche lo stato Meta grezzo per diagnosi."""
    import requests
    if not whatsapp_number:
        whatsapp_number = frappe.db.get_value(
            "WhatsApp Number", {"provider": "Meta", "is_active": 1}, "name") \
            or frappe.db.get_value("WhatsApp Number", {"is_active": 1}, "name")
    if not whatsapp_number:
        return {"ok": False, "reason": "nessun WhatsApp Number configurato"}
    wa = frappe.get_doc("WhatsApp Number", whatsapp_number)
    waba = frappe.conf.get("wa_business_account_id") or getattr(wa, "waba_id", None)
    if not waba:
        # ricava il WABA id dall'ultimo webhook grezzo (l'entry.id è il WABA)
        import json as _json
        for L in frappe.get_all("WABA Webhook Log", fields=["payload"],
                                order_by="creation desc", limit=50):
            try:
                p = _json.loads(L.payload)
            except Exception:
                continue
            for e in p.get("entry", []):
                if e.get("id"):
                    waba = e["id"]
                    break
            if waba:
                break
    if not waba:
        return {"ok": False, "reason": "WABA id non determinato"}
    token = get_decrypted_password("WhatsApp Number", wa.name, "meta_access_token")
    r = requests.get(
        f"https://graph.facebook.com/v21.0/{waba}/message_templates",
        headers={"Authorization": f"Bearer {token}"},
        params={"fields": "name,status,category", "limit": 200}, timeout=30)
    if r.status_code != 200:
        return {"ok": False, "reason": f"HTTP {r.status_code}: {(r.text or '')[:160]}"}
    remote = {t.get("name"): t for t in (r.json() or {}).get("data", [])}
    changed = []
    for tpl in frappe.get_all("WhatsApp Template",
                              fields=["name", "meta_template_name", "template_name", "is_active"]):
        key = tpl.meta_template_name or tpl.template_name or tpl.name
        rt = remote.get(key)
        if not rt:
            continue
        want = 1 if rt.get("status") in _TEMPLATE_ACTIVE_STATUSES else 0
        if want != (tpl.is_active or 0):
            frappe.db.set_value("WhatsApp Template", tpl.name, "is_active", want)
            changed.append({"template": tpl.name, "meta_status": rt.get("status"), "is_active": want})
    frappe.db.commit()
    return {"ok": True, "waba": waba, "totale": len(remote), "aggiornati": changed}


def scheduled_sync_template_status():
    """Job giornaliero: tiene allineato lo stato dei template con Meta."""
    try:
        return sync_template_status()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "sync_template_status")


# ─────────── ripiego automatico fuori finestra 24h (errore 131047) ───────────
# Template usato per riagganciare il contatto quando un messaggio libero fallisce
# perche' sono passate 24h. Il jolly: riapre la conversazione senza svelare il merito.
_FALLBACK_TEMPLATE = "contatto_operatore"
_MESI_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _data_it(dt):
    from frappe.utils import get_datetime
    d = get_datetime(dt) if dt else now_datetime()
    return f"{d.day} {_MESI_IT[d.month]} {d.year}"


def _maybe_auto_template(lead_name: str, wa_msg_id: str, note: str = ""):
    """Un messaggio libero e' fallito. Se e' per la finestra 24h (131047), reinvia
    automaticamente il contatto come TEMPLATE (che la finestra la ignora), cosi' il
    cliente non resta irraggiungibile. Protezioni: solo 131047; mai su un messaggio
    che e' gia' un template (anti-loop); una volta per conversazione (cooldown);
    solo se il template e' approvato. Disattivabile: site_config wa_auto_template_fallback=0."""
    if not frappe.conf.get("wa_auto_template_fallback", 1):
        return
    if "131047" not in (note or ""):
        return  # altri errori (numero invalido, ecc.): un template non aiuta
    orig = frappe.db.get_value("Intel Lead Message", {"wa_message_id": wa_msg_id}, "content") or ""
    if orig.strip().startswith("[template:"):
        return  # anti-loop: il messaggio fallito era gia' un template
    if not frappe.db.get_value("WhatsApp Template", _FALLBACK_TEMPLATE, "is_active"):
        return  # template non approvato/attivo: resta solo l'alert
    key = f"wa_tmpl_fb:{lead_name}"
    if frappe.cache().get_value(key, use_local_cache=False):
        return  # gia' riagganciato di recente
    ttl = int(frappe.conf.get("wa_auto_template_fallback_cooldown") or 43200)  # 12h
    frappe.cache().set_value(key, "1", expires_in_sec=ttl)
    frappe.enqueue("thanatos_intel.ingest.whatsapp_send._send_fallback_template",
                   queue="short", lead_name=lead_name, enqueue_after_commit=True)


def _send_fallback_template(lead_name: str):
    """Job: invia il template di riaggancio come sistema (sent_by=Administrator)."""
    import json
    lead = frappe.db.get_value(
        "Intel Lead", lead_name,
        ["source_name", "source_identifier", "received_at"], as_dict=True)
    if not lead:
        return
    name = (lead.source_name or "").strip()
    if not any(ch.isalpha() for ch in name):
        name = "Cliente"
    params = [name, _data_it(lead.received_at)]
    prev_user = frappe.session.user
    try:
        frappe.set_user("Administrator")
        send_template(lead_name, _FALLBACK_TEMPLATE, "it", body_params=json.dumps(params))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "auto template fallback send")
    finally:
        frappe.set_user(prev_user)


@frappe.whitelist()
def send_template(lead_name: str, template_name: str, language: str = "it",
                  body_params: str | None = None) -> dict:
    """Invia un template Meta approvato (per scrivere fuori dalla finestra 24h).
    body_params: lista JSON di valori per i segnaposto {{1}},{{2}}... del corpo."""
    import json
    lead = frappe.get_doc("Intel Lead", lead_name)
    if lead.source_type != "WhatsApp":
        frappe.throw(_("Questo lead non è di tipo WhatsApp."))
    to_number = (lead.source_identifier or "").strip()
    wa_doc = frappe.get_doc("WhatsApp Number", lead.whatsapp_number)
    phone_number_id = wa_doc.meta_phone_number_id
    access_token = get_decrypted_password("WhatsApp Number", wa_doc.name, "meta_access_token")
    if not phone_number_id or not access_token:
        frappe.throw(_("Configurazione Meta mancante."))

    template = {"name": template_name, "language": {"code": language}}
    params = json.loads(body_params) if body_params else []
    if params:
        template["components"] = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in params],
        }]

    import requests
    resp = requests.post(
        f"https://graph.facebook.com/v21.0/{phone_number_id}/messages",
        json={"messaging_product": "whatsapp", "to": to_number.lstrip("+").replace(" ", ""),
              "type": "template", "template": template},
        headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    data = resp.json()
    ok = resp.status_code == 200 and data.get("messages")
    mid = data["messages"][0].get("id", "") if ok else ""

    lead.append("messages", {
        "direction": "Outbound", "sent_at": now_datetime(),
        "content": f"[template: {template_name}]",
        "status": "Inviato" if ok else "Fallito",
        "sent_by": frappe.session.user, "wa_message_id": mid,
    })
    lead.db_set("last_message_at", now_datetime(), notify=False)
    lead.save(ignore_permissions=True)
    frappe.db.commit()
    if not ok:
        frappe.throw(_("Errore invio template: {0}").format(
            data.get("error", {}).get("message", str(data))))
    return {"ok": True, "message_id": mid}


def _send_via_twilio(wa_doc, to_number: str, text: str) -> dict:
    account_sid = wa_doc.twilio_account_sid
    auth_token = get_decrypted_password(
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
