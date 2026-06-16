import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/vault"
        raise frappe.Redirect

    from thanatos_intel.workflow.vault import my_vault
    from thanatos_intel.workflow.api import _is_operator
    v = my_vault()
    context.vault = v
    context.items = v.get("items") or []
    context.identity = v.get("identity") or {}
    context.has_client = bool(v.get("client"))
    context.is_operator = _is_operator(frappe.session.user)
    import frappe.sessions; context.csrf_token = frappe.sessions.get_csrf_token()
    context.title = "Il mio archivio documenti — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
