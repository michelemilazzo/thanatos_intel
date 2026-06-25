import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/prova-email"
        raise frappe.Redirect

    from thanatos_intel.permissions import is_full_access, visible_case_names
    user = frappe.session.user
    if is_full_access(user):
        cases = frappe.get_all("Investigation Case", fields=["name", "case_number", "case_title"],
                               order_by="creation desc", limit=50)
    else:
        names = visible_case_names(user) or []
        cases = frappe.get_all("Investigation Case", filters={"name": ["in", names]},
                               fields=["name", "case_number", "case_title"],
                               order_by="creation desc", limit=50) if names else []
    context.cases = cases
    context.preselect = frappe.form_dict.get("case") if frappe.form_dict.get("case") in [c.name for c in cases] else None
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Invia email come prova — Thanatos Intel"
    return context
