import frappe

DISCLAIMER = ("Thanatos performs investigative, due diligence, compliance and "
              "eligibility assessment services only. Thanatos does NOT issue, "
              "sell, broker or guarantee diplomatic, consular, governmental or "
              "identity documents. Any decision is exclusively subject to "
              "competent public authorities and applicable law.")


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
    context.my_cases = frappe.get_all("Diplomatic Eligibility Case",
        fields=["name", "applicant", "country", "request_type",
                "workflow_state", "risk_score", "risk_band", "final_decision",
                "modified"],
        order_by="modified desc", limit=30)
    return context
