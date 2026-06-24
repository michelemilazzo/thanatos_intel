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
    context.title = "SEO &amp; Analytics — Thanatos"

    try:
        days = int(frappe.form_dict.get("days") or 30)
    except Exception:
        days = 30
    if days not in (7, 30, 90):
        days = 30
    context.days = days

    from thanatos_intel.seo_dashboard import get_dashboard
    try:
        context.dash = get_dashboard(days)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "seo page dashboard")
        context.dash = {}

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
