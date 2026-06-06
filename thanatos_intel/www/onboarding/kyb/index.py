import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/onboarding/kyb"
        raise frappe.Redirect
    user = frappe.session.user
    name = frappe.db.get_value("Investigation Client",
                               {"platform_user": user}, "name")
    if not name:
        frappe.local.flags.redirect_location = "/signup"
        raise frappe.Redirect
    c = frappe.get_doc("Investigation Client", name)
    if c.client_type == "Individual":
        frappe.local.flags.redirect_location = "/onboarding/kyc"
        raise frappe.Redirect
    context.client = c
    context.type_label = {
        "Company": "Azienda",
        "Law Firm": "Studio legale",
        "Accounting Firm": "Studio commercialista",
        "Other": "Ente",
    }.get(c.client_type, c.client_type)
