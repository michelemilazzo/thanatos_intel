"""Note vocali WhatsApp → download media Meta + trascrizione AssemblyAI.

Flusso (background job da webhook):
  1. scarica l'audio dal media_id Meta (URL temporaneo + auth)
  2. lo allega come File all'Intel Lead
  3. trascrive con AssemblyAI (language detection)
  4. aggiorna il contenuto del lead e dell'ultimo messaggio inbound con la trascrizione
"""
import frappe
from frappe.utils.password import get_decrypted_password


_GRAPH = "https://graph.facebook.com/v21.0"


def _resolve_token(wa_phone: str | None) -> tuple[str, str]:
    """Restituisce (access_token, wa_doc_name) del numero Meta da usare."""
    name = wa_phone
    if not name:
        name = frappe.db.get_value(
            "WhatsApp Number",
            {"provider": "Meta Cloud API", "is_active": 1},
            "name",
        )
    if not name:
        raise ValueError("Nessun WhatsApp Number Meta attivo")
    token = get_decrypted_password("WhatsApp Number", name, "meta_access_token")
    if not token:
        raise ValueError("meta_access_token mancante")
    return token, name


def download_meta_media(media_id: str, access_token: str) -> tuple[bytes, str]:
    """Scarica i bytes del media da Meta. Restituisce (content, mime_type)."""
    import requests

    meta = requests.get(
        f"{_GRAPH}/{media_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    meta.raise_for_status()
    info = meta.json()
    url = info.get("url")
    mime = info.get("mime_type", "audio/ogg")
    if not url:
        raise ValueError("URL media non disponibile")

    binr = requests.get(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=60,
    )
    binr.raise_for_status()
    return binr.content, mime


def _transcribe(content: bytes, api_key: str) -> str:
    import requests
    import time

    up = requests.post(
        "https://api.assemblyai.com/v2/upload",
        headers={"authorization": api_key},
        data=content,
        timeout=120,
    )
    up.raise_for_status()
    audio_url = up.json()["upload_url"]

    job = requests.post(
        "https://api.assemblyai.com/v2/transcript",
        json={"audio_url": audio_url, "language_detection": True},
        headers={"authorization": api_key, "content-type": "application/json"},
        timeout=30,
    )
    job.raise_for_status()
    job_id = job.json()["id"]

    for _ in range(90):  # max ~7.5 min
        time.sleep(5)
        poll = requests.get(
            f"https://api.assemblyai.com/v2/transcript/{job_id}",
            headers={"authorization": api_key}, timeout=15,
        ).json()
        if poll.get("status") == "completed":
            return poll.get("text", "") or ""
        if poll.get("status") == "error":
            raise ValueError(poll.get("error", "errore AssemblyAI"))
    raise TimeoutError("Timeout trascrizione nota vocale")


def process_voice_note(lead_name: str, media_id: str, wa_phone: str | None = None):
    """Background job: scarica, allega e trascrive la nota vocale."""
    try:
        token, _ = _resolve_token(wa_phone)
        content, mime = download_meta_media(media_id, token)

        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
               "audio/amr": "amr", "audio/wav": "wav"}.get(mime.split(";")[0], "ogg")
        fname = f"wa-voice-{media_id[:12]}.{ext}"

        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": fname,
            "attached_to_doctype": "Intel Lead",
            "attached_to_name": lead_name,
            "is_private": 1,
            "content": content,
        }).insert(ignore_permissions=True)

        text = ""
        api_key = frappe.conf.get("assemblyai_api_key")
        if api_key:
            try:
                text = _transcribe(content, api_key)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"voice transcribe {lead_name}")

        label = f"🎤 {text}" if text else "🎤 [nota vocale ricevuta — trascrizione non disponibile]"

        # aggiorna l'ultimo messaggio inbound del lead
        msg = frappe.db.sql(
            """SELECT name FROM `tabIntel Lead Message`
               WHERE parent=%s AND direction='Inbound'
               ORDER BY sent_at DESC LIMIT 1""",
            (lead_name,), as_dict=True,
        )
        if msg:
            frappe.db.set_value("Intel Lead Message", msg[0].name, {
                "content": label,
                "media_url": file_doc.file_url,
            })

        # aggiorna il contenuto del lead se era placeholder
        cur = frappe.db.get_value("Intel Lead", lead_name, "content") or ""
        if cur.strip() in ("[audio]", "[media]", ""):
            frappe.db.set_value("Intel Lead", lead_name, "content", label)

        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"process_voice_note {lead_name}")
