import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/asset"
        raise frappe.Redirect
    from thanatos_intel.reporting import asset_value as av
    context.card = av.card_data()
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Asset Cloud — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context
