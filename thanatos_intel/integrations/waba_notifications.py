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


def _case_amount(case_name: str):
    """Best-effort importo da richiedere: importo non saldato dell'ultima fattura del
    cliente del caso (ARES Sales Invoice). None se non determinabile."""
    try:
        client = frappe.db.get_value("Investigation Case", case_name, "client")
        customer = frappe.db.get_value("Investigation Client", client, "customer") if client else None
        if not customer:
            return None
        inv = frappe.get_all("Sales Invoice",
                             filters={"customer": customer, "docstatus": ["<", 2]},
                             fields=["grand_total", "outstanding_amount"],
                             order_by="creation desc", limit=1)
        if inv:
            return inv[0].outstanding_amount or inv[0].grand_total
    except Exception:
        pass
    return None


def notify_payment_request(case_name: str, amount: float = None, currency: str = "EUR"):
    """Notifica il cliente del pagamento richiesto. Se `amount` non è passato (es. dal
    motore workflow allo step «pay», che non conosce l'importo), lo deriva dall'ultima
    fattura del cliente; se non c'è un importo certo non invia (no template fuorviante)."""
    if amount is None:
        amount = _case_amount(case_name)
    if amount is None:
        return False
    phone = _get_client_phone(case_name)
    if phone:
        _send_whatsapp(phone, "thanatos_payment_request", [case_name, f"{float(amount):.2f}", currency])
    return True


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
