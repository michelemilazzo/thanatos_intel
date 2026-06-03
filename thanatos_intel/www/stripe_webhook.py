import json
import frappe
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True, methods=["POST"])
def index():
    """Stripe webhook endpoint: /api/method/thanatos_intel.www.stripe_webhook.index"""
    payload = frappe.request.get_data() or b""
    sig = frappe.get_request_header("Stripe-Signature") or ""

    event = None
    sig_valid = False
    error = None
    status = "received"

    from thanatos_intel.integrations.stripe_bridge import verify_webhook_signature, handle_event
    try:
        event = verify_webhook_signature(payload, sig)
        sig_valid = True
    except Exception as e:
        error = f"signature_invalid: {e}"
        status = "failed"

    if event:
        try:
            handle_event(event)
            status = "processed"
        except Exception as e:
            error = str(e)[:1000]
            status = "failed"
            frappe.log_error(frappe.get_traceback(), "Stripe webhook handler")

    try:
        ev_id = (event or {}).get("id") or f"unverified_{now_datetime().isoformat()}"
        ev_type = (event or {}).get("type") or "invalid"
        if not frappe.db.exists("Stripe Event", ev_id):
            doc = frappe.get_doc({
                "doctype": "Stripe Event",
                "event_id": ev_id,
                "event_type": ev_type,
                "received_at": now_datetime(),
                "status": status,
                "is_signature_valid": 1 if sig_valid else 0,
                "payload": (payload[:60000] or b"").decode("utf-8", errors="replace"),
                "error_message": error,
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Stripe Event persist")

    if error and not sig_valid:
        frappe.local.response["http_status_code"] = 400
        return {"error": error}

    return {"received": True, "status": status}
