"""Canale Telegram per le notifiche pratiche (pluggabile).

Attivo solo se in site_config c'è `telegram_bot_token` e il cliente ha un
`telegram_chat_id`. Altrimenti no-op. Stesso pattern di waba_notifications.
"""
import frappe


def _chat_id(case_name):
    client = frappe.db.get_value("Investigation Case", case_name, "client")
    if not client:
        return None
    try:
        meta = frappe.get_meta("Investigation Client")
        if not meta.get_field("telegram_chat_id"):
            return None
        return frappe.db.get_value("Investigation Client", client, "telegram_chat_id")
    except Exception:
        return None


def notify_telegram(case_name, text):
    token = frappe.conf.get("telegram_bot_token")
    if not token:
        return False
    chat = _chat_id(case_name)
    if not chat:
        return False
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                      timeout=10)
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "telegram_channel")
        return False
