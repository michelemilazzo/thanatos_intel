"""Ponte Frappe ↔ media server WhatsApp Calling (aiortc su ai-core).

- register_recording: il media server, a fine chiamata, carica la registrazione →
  crea/aggiorna Call Log + avvia trascrizione con diarizzazione.
- operator_join: il Centralino inoltra l'SDP offer dell'operatore al media server
  per unirsi alla chiamata (bridge audio live).
- forward_incoming_call: chiamato dal webhook (evento connect) per accettare la
  chiamata sul media server.
"""
import json
import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password


def _media_url():
    return frappe.conf.get("wa_calling_url", "http://10.10.0.4:18093")


def forward_incoming_call(call_id, pnid, frm, sdp, wa_number=None):
    """Inoltra l'evento connect al media server che accetta la chiamata."""
    import requests
    name = wa_number.phone_number if wa_number else frappe.db.get_value(
        "WhatsApp Number", {"meta_phone_number_id": pnid, "is_active": 1}, "name")
    if not name:
        return {"ok": False, "error": "numero non trovato"}
    token = get_decrypted_password("WhatsApp Number", name, "meta_access_token")
    base = frappe.utils.get_url()
    r = requests.post(
        f"{_media_url()}/incoming",
        json={"call_id": call_id, "pnid": pnid, "from": frm, "sdp": sdp,
              "token": token, "frappe_url": base},
        timeout=20,
    )
    return r.json()


@frappe.whitelist()
def operator_join(call_id, sdp):
    """Il Centralino: l'operatore si unisce alla chiamata. Ritorna l'SDP answer."""
    import requests
    r = requests.post(f"{_media_url()}/operator/offer",
                      json={"call_id": call_id, "sdp": sdp}, timeout=20)
    return r.json()


@frappe.whitelist(allow_guest=True)
def register_recording():
    """Chiamato dal media server a fine chiamata: salva la registrazione → Call Log + trascrizione.
    Auth: header X-WA-Calling-Secret."""
    secret = frappe.get_request_header("X-WA-Calling-Secret", "")
    if not secret or secret != frappe.conf.get("wa_calling_secret"):
        frappe.throw(_("Non autorizzato"), frappe.PermissionError)

    frm = frappe.form_dict.get("from_number", "")
    call_id = frappe.form_dict.get("call_id", "")
    duration = int(frappe.form_dict.get("duration", 0) or 0)
    answered = int(frappe.form_dict.get("answered", 0) or 0)
    files = frappe.request.files
    audio = files.get("file") if files else None

    # trova/crea la scheda contatto (numero + nominativo) e recupera i dati
    from thanatos_intel.ingest.contacts import ensure_contact_from_wa
    n = frm if frm.startswith("+") else "+" + frm
    contact = ensure_contact_from_wa(frm, "", "Chiamata WhatsApp")
    caller_name = frappe.db.get_value("Intelligence Contact", contact, "full_name") if contact else ""
    contact_client = frappe.db.get_value("Intelligence Contact", contact, "linked_entity") if contact else None

    # Call Log già creato all'arrivo? aggiorna; altrimenti crea
    existing = frappe.db.get_value("Call Log", {"summary": ["like", f"%{call_id}%"]}, "name")
    if existing:
        doc = frappe.get_doc("Call Log", existing)
    else:
        doc = frappe.get_doc({
            "doctype": "Call Log", "called_at": frappe.utils.now_datetime(),
            "direction": "Entrante", "caller_number": n,
            "summary": f"Chiamata WhatsApp · id {call_id}",
        })
        doc.insert(ignore_permissions=True)

    # popola più campi possibili
    doc.db_set("caller_number", n)
    if caller_name:
        doc.db_set("caller_name", caller_name)
    if contact:
        doc.db_set("linked_contact", contact)
    doc.db_set("handled_by", frappe.session.user if frappe.session.user != "Guest" else "Administrator")
    doc.db_set("outcome", "Risposta" if answered else "Messaggio vocale")
    doc.db_set("duration_seconds", duration % 60)
    doc.db_set("duration_minutes", duration // 60)

    if audio:
        import os
        content = audio.stream.read()
        fname = f"wa-call-{call_id[:18]}.ogg"
        # 1. audio su StorageBox (box autoritativo, non riempie il disco del bench)
        box_dir = frappe.conf.get("call_recordings_box", "/mnt/thanatos-box/call-recordings")
        file_url = f"/private/files/{fname}"
        try:
            os.makedirs(box_dir, exist_ok=True)
            box_path = os.path.join(box_dir, fname)
            with open(box_path, "wb") as f:
                f.write(content)
            # 2. symlink nel private/files del sito → StorageBox (Frappe serve seguendo il link)
            link_path = frappe.get_site_path("private", "files", fname)
            if os.path.islink(link_path) or os.path.exists(link_path):
                os.remove(link_path)
            os.symlink(box_path, link_path)
            fdoc = frappe.get_doc({
                "doctype": "File", "file_name": fname, "file_url": file_url,
                "attached_to_doctype": "Call Log", "attached_to_name": doc.name,
                "is_private": 1,
            }).insert(ignore_permissions=True)
        except Exception:
            # fallback: salva nel filesystem del bench se il box non è disponibile
            frappe.log_error(frappe.get_traceback(), "call rec box save")
            fdoc = frappe.get_doc({
                "doctype": "File", "file_name": fname,
                "attached_to_doctype": "Call Log", "attached_to_name": doc.name,
                "is_private": 1, "content": content,
            }).insert(ignore_permissions=True)
            file_url = fdoc.file_url
        doc.db_set("audio_file", file_url)
        doc.db_set("transcription_status", "In elaborazione")
        frappe.db.commit()
        # trascrizione con diarizzazione (Whisper locale)
        frappe.enqueue("thanatos_intel.ingest.transcription.transcribe_call_log",
                       queue="long", timeout=900, call_log_name=doc.name)
    frappe.db.commit()
    return {"ok": True, "call_log": doc.name}
