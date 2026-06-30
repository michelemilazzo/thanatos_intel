import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/servizi"
        raise frappe.Redirect
    from thanatos_intel.osint.self_service import list_services
    d = list_services()
    context.services = d.get("services") or []
    context.wallet = d.get("wallet") or 0
    context.has_client = bool(d.get("client"))
    context.title = "Servizi — acquista documenti"
    context.lang = frappe.local.lang or "it"
    return context
