"""Card capture page — Stripe SetupIntent flow."""
import frappe

no_cache = 1


def get_context(context):
    context.body_class = "ob-page"
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/onboarding/card"
        raise frappe.Redirect

    user = frappe.session.user
    client_name = frappe.db.get_value("Investigation Client",
                                      {"platform_user": user}, "name")
    if not client_name:
        frappe.local.flags.redirect_location = "/signup"
        raise frappe.Redirect

    c = frappe.get_doc("Investigation Client", client_name)
    context.client = c
    context.is_individual = (c.client_type == "Individual")
    context.stripe_publishable_key = frappe.conf.get("stripe_publishable_key") or ""
    context.next_step = "/onboarding/kyc" if context.is_individual else "/onboarding/kyb"
    context.client_type_label = {
        "Individual": "Cliente privato",
        "Company": "Azienda",
        "Law Firm": "Studio legale",
        "Accounting Firm": "Studio commercialista",
        "Other": "Altro",
    }.get(c.client_type, c.client_type)
