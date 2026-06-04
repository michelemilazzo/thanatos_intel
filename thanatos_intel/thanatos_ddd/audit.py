"""Audit hooks: ogni status change e decisione su Diplomatic DD Case
crea automaticamente un record Ddd Audit Log immutabile."""
import frappe
from frappe.utils import now_datetime

TRACKED_FIELDS = {"workflow_state", "final_decision", "risk_score",
                  "risk_band", "decision_notes"}


def _ip():
    try:
        return frappe.local.request.headers.get("X-Forwarded-For") \
            or frappe.local.request.remote_addr
    except Exception:
        return None


def on_update_case(doc, method=None):
    if not doc.get_doc_before_save():
        return
    before = doc.get_doc_before_save()
    for f in TRACKED_FIELDS:
        old, new = before.get(f), doc.get(f)
        if (old or "") != (new or ""):
            frappe.get_doc({
                "doctype": "Ddd Audit Log",
                "ddd_case": doc.name,
                "ts": now_datetime(),
                "user": frappe.session.user,
                "event_type": "Status Change" if f == "workflow_state" else
                              "Decision" if f == "final_decision" else
                              "Risk Override" if f.startswith("risk") else "Note",
                "old_value": str(old or "")[:140],
                "new_value": str(new or "")[:140],
                "reason": f"campo {f}",
                "ip": _ip(),
            }).insert(ignore_permissions=True)


def on_after_insert_case(doc, method=None):
    frappe.get_doc({
        "doctype": "Ddd Audit Log",
        "ddd_case": doc.name,
        "ts": now_datetime(),
        "user": frappe.session.user,
        "event_type": "Status Change",
        "new_value": "Created",
        "reason": "case opening",
        "ip": _ip(),
    }).insert(ignore_permissions=True)
