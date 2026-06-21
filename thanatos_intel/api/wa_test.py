"""Endpoint di test per WhatsApp + trascrizione/diarizzazione (pagina /app/wa-test)."""
import json
import frappe
from frappe import _
from frappe.utils.password import get_decrypted_password


@frappe.whitelist()
def system_status():
    """Stato dei componenti: Whisper, numero WhatsApp, token, webhook."""
    import requests
    out = {}

    # Whisper locale
    url = frappe.conf.get("whisper_url", "http://10.10.0.4:18092")
    try:
        r = requests.get(f"{url}/health", timeout=5)
        out["whisper"] = {"ok": r.status_code == 200, "info": r.json()}
    except Exception as e:
        out["whisper"] = {"ok": False, "error": str(e)[:120]}

    # Numero WhatsApp + token
    num = frappe.db.get_value(
        "WhatsApp Number", {"provider": "Meta Cloud API", "is_active": 1},
        ["name", "display_name", "meta_phone_number_id"], as_dict=True)
    if num:
        tok = get_decrypted_password("WhatsApp Number", num.name, "meta_access_token")
        out["whatsapp_number"] = {
            "ok": bool(tok), "phone": num.name, "display": num.display_name,
            "phone_number_id": num.meta_phone_number_id, "token_set": bool(tok),
        }
        # verifica token live
        if tok:
            try:
                vr = requests.get(
                    f"https://graph.facebook.com/v21.0/{num.meta_phone_number_id}",
                    params={"access_token": tok}, timeout=10)
                d = vr.json()
                out["whatsapp_number"]["token_valid"] = vr.status_code == 200
                out["whatsapp_number"]["verified_name"] = d.get("verified_name", "")
            except Exception as e:
                out["whatsapp_number"]["token_valid"] = False
    else:
        out["whatsapp_number"] = {"ok": False, "error": "nessun numero Meta attivo"}

    out["webhook_token_set"] = bool(frappe.conf.get("whatsapp_ingest_token"))
    return out


@frappe.whitelist()
def transcribe_file(file_url: str, diarize: int = 1, num_speakers: int = 2):
    """Trascrive (con diarizzazione) un file audio allegato. Ritorna segmenti con voci."""
    import requests
    from frappe.utils.file_manager import get_file

    if not file_url:
        frappe.throw(_("Nessun file."))
    _fname, content = get_file(file_url)
    url = frappe.conf.get("whisper_url", "http://10.10.0.4:18092")
    r = requests.post(
        f"{url}/transcribe",
        files={"audio": ("test.audio", content)},
        data={"diarize": "true" if int(diarize) else "false",
              "num_speakers": int(num_speakers)},
        timeout=900,
    )
    r.raise_for_status()
    return r.json()


@frappe.whitelist()
def send_test_message(phone: str, text: str):
    """Invia un messaggio WhatsApp di test a un numero (deve aver scritto nelle 24h)."""
    import requests
    num = frappe.db.get_value(
        "WhatsApp Number", {"provider": "Meta Cloud API", "is_active": 1},
        ["name", "meta_phone_number_id"], as_dict=True)
    if not num:
        frappe.throw(_("Nessun numero Meta attivo."))
    tok = get_decrypted_password("WhatsApp Number", num.name, "meta_access_token")
    to = phone.lstrip("+").replace(" ", "").replace("-", "")
    r = requests.post(
        f"https://graph.facebook.com/v21.0/{num.meta_phone_number_id}/messages",
        json={"messaging_product": "whatsapp", "to": to,
              "type": "text", "text": {"body": text}},
        headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    d = r.json()
    if r.status_code == 200 and d.get("messages"):
        return {"ok": True, "message_id": d["messages"][0].get("id", "")}
    return {"ok": False, "error": d.get("error", {}).get("message", str(d))}
