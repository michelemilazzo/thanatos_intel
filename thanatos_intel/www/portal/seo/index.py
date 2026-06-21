import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/seo"
        raise frappe.Redirect
    from thanatos_intel.analytics import _is_staff
    if not _is_staff():
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
    context.title = "SEO — Thanatos"
    context.keywords = frappe.get_all(
        "SEO Keyword", fields=["name", "keyword", "origin", "is_active", "weight"],
        order_by="is_active desc, weight desc, keyword asc", limit_page_length=0)
    context.n_active = sum(1 for k in context.keywords if k.is_active)
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.no_cache = 1
    return context
