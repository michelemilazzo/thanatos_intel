"""Signup page Thanatos — custom form con campi GDPR/AML.

Endpoint POST: thanatos_intel.api.signup.do_signup
"""
import frappe

no_cache = 1


def get_context(context):
    context.body_class = "signup-page"
    if frappe.session.user != "Guest":
        # already logged in → portal
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect

    context.client_types = [
        {"value": "Individual",       "label": "Cliente privato"},
        {"value": "Company",          "label": "Azienda"},
        {"value": "Law Firm",         "label": "Studio legale"},
        {"value": "Accounting Firm",  "label": "Studio commercialista"},
        {"value": "Other",            "label": "Altro (investigatore, consulente, ecc.)"},
    ]
    context.languages = [
        {"value": "Italian",  "label": "Italiano"},
        {"value": "English",  "label": "English"},
        {"value": "Romanian", "label": "Română"},
    ]
    context.countries = ["Italy", "Romania", "Bulgaria", "Albania",
                         "France", "Germany", "Spain", "United Kingdom",
                         "Switzerland", "Other"]
