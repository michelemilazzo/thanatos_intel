import frappe

no_cache = 1


def get_context(context):
    context.body_class = "ob-page"
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/onboarding/kyc"
        raise frappe.Redirect
    user = frappe.session.user
    name = frappe.db.get_value("Investigation Client",
                               {"platform_user": user}, "name")
    if not name:
        frappe.local.flags.redirect_location = "/signup"
        raise frappe.Redirect
    c = frappe.get_doc("Investigation Client", name)
    if c.client_type != "Individual":
        frappe.local.flags.redirect_location = "/onboarding/kyb"
        raise frappe.Redirect
    context.client = c
