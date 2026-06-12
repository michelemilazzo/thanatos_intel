import frappe
from frappe import _

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/segnala"
        raise frappe.Redirect
    context.client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    context.balance = frappe.db.get_value("Investigation Client", context.client, "service_credit") if context.client else 0
    context.bonus = frappe.db.get_single_value("Thanatos Billing Settings", "report_bonus_amount") or 2
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Segnala alla blacklist — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context


@frappe.whitelist(methods=["POST"])
def submit_report(entry_type, entry_value, reason, evidence=None):
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    if not client:
        frappe.throw(_("Il tuo account non è collegato a un profilo cliente."))
    entry_value = (entry_value or "").strip()
    if not entry_value or not (reason or "").strip():
        frappe.throw(_("Valore e motivo sono obbligatori."))
    doc = frappe.get_doc({
        "doctype": "Blacklist Report", "reporter": client, "entry_type": entry_type,
        "entry_value": entry_value, "reason": reason, "status": "In Review",
        "evidence": (evidence or "").strip() or None,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}
