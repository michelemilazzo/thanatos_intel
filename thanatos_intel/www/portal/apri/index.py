import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/apri"
        raise frappe.Redirect

    from thanatos_intel.workflow.api import available_blueprints, _client_for_user, _is_operator
    context.blueprints = available_blueprints()
    cl = _client_for_user(frappe.session.user)
    context.has_client = bool(cl) or _is_operator(frappe.session.user)
    context.title = "Apri una pratica — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
