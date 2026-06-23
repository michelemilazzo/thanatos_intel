import frappe

from thanatos_intel.thanatos_ddd.portal_acl import is_ddd_staff, client_applicants

DISCLAIMER = ("Thanatos performs investigative, due diligence, compliance and "
              "eligibility assessment services only. Thanatos does NOT issue, "
              "sell, broker or guarantee diplomatic, consular, governmental or "
              "identity documents. Any decision is exclusively subject to "
              "competent public authorities and applicable law.")

CASE_FIELDS = ["name", "applicant", "country", "request_type",
               "workflow_state", "risk_score", "risk_band", "final_decision",
               "modified"]


def get_context(context):
    context.no_cache = 1
    context.title = "Thanatos · Diplomatic Due Diligence"
    context.disclaimer = DISCLAIMER
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/ddd"
        raise frappe.Redirect
    context.countries = frappe.get_all("Country Framework",
        filters={"is_active": 1}, fields=["name", "iso3", "diplomatic_authority"],
        order_by="name")
    if is_ddd_staff():
        context.my_cases = frappe.get_all("Diplomatic Eligibility Case",
            fields=CASE_FIELDS, order_by="modified desc", limit=30)
    else:
        apps = client_applicants()
        context.my_cases = frappe.get_all("Diplomatic Eligibility Case",
            filters={"applicant": ["in", apps]}, fields=CASE_FIELDS,
            order_by="modified desc", limit=30) if apps else []
    return context
