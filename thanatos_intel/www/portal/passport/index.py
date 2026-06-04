import frappe

def get_context(context):
    context.no_cache = 1
    context.title = "Passport Analyzer"
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/passport"
        raise frappe.Redirect
    context.recent = frappe.get_all("Passport Analysis",
        fields=["name", "passport_number", "passport_type", "issuing_country",
                "is_diplomatic", "expiry", "risk_score", "verdict", "modified"],
        order_by="creation desc", limit=20)
    return context
