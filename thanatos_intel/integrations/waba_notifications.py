"""Notifiche WhatsApp Business per eventi pipeline Thanatos Intel.

Configurazione in site_config.json:
  "waba_enabled": 1,
  "waba_phone_id": "...",        # WhatsApp Business Phone Number ID
  "waba_token": "...",           # Bearer token Meta Cloud API
  "waba_template_ns": "..."      # Template namespace (opzionale)

Templates da creare su Meta Business Manager:
  - thanatos_mandate_ready: "Il mandato per il caso {{1}} è pronto per la firma."
  - thanatos_payment_request: "Preventivo approvato per {{1}}. Importo: {{2}} {{3}}."
  - thanatos_report_ready: "Il report del caso {{1}} è disponibile nel portale."
  - thanatos_step_action: "Azione richiesta per il caso {{1}}: {{2}}."
"""

import frappe


def _is_enabled() -> bool:
    return bool(frappe.conf.get("waba_enabled"))


def _get_client_phone(case_name: str) -> str | None:
    """Restituisce il numero di telefono del cliente del caso."""
    try:
        client_name = frappe.db.get_value("Investigation Case", case_name, "client")
        if not client_name:
            return None
        phone = frappe.db.get_value("Investigation Client", client_name, "phone")
        return phone
    except Exception:
        return None


def _send_whatsapp(to_phone: str, template: str, params: list) -> bool:
    """Invia messaggio WhatsApp tramite Meta Cloud API."""
    if not _is_enabled():
        return False
    phone_id = frappe.conf.get("waba_phone_id", "")
    token = frappe.conf.get("waba_token", "")
    if not phone_id or not token:
        return False

    import requests
    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone.replace("+", "").replace(" ", ""),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": "it"},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": str(p)} for p in params]
            }]
        }
    }
    try:
        resp = requests.post(url, json=payload,
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=10)
        if not resp.ok:
            frappe.log_error(resp.text, "waba_notifications send error")
        return resp.ok
    except Exception:
        frappe.log_error(frappe.get_traceback(), "waba_notifications exception")
        return False


def notify_mandate_ready(case_name: str):
    """Notifica il cliente che il mandato è pronto per la firma."""
    phone = _get_client_phone(case_name)
    if phone:
        _send_whatsapp(phone, "thanatos_mandate_ready", [case_name])


def notify_payment_request(case_name: str, amount: float, currency: str = "EUR"):
    """Notifica il cliente del pagamento richiesto."""
    phone = _get_client_phone(case_name)
    if phone:
        _send_whatsapp(phone, "thanatos_payment_request", [case_name, f"{amount:.2f}", currency])


def notify_report_ready(case_name: str):
    """Notifica il cliente che il report è disponibile."""
    phone = _get_client_phone(case_name)
    if phone:
        _send_whatsapp(phone, "thanatos_report_ready", [case_name])


def notify_step_action(case_name: str, step_label: str):
    """Notifica il cliente che c'è un'azione richiesta."""
    phone = _get_client_phone(case_name)
    if phone:
        _send_whatsapp(phone, "thanatos_step_action", [case_name, step_label])


def on_investigation_report_update(doc, method=None):
    """Hook: quando un report diventa Available/Final, notifica il cliente."""
    if doc.get("report_status") in ("Available", "Final", "Delivered") and doc.get("investigation_case"):
        try:
            notify_report_ready(doc.investigation_case)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "waba on_report_update")
