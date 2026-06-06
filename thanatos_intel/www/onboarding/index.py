"""Onboarding orchestrator — redirects to next step by Investigation Client state."""
import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/onboarding"
        raise frappe.Redirect

    user = frappe.session.user
    client_name = frappe.db.get_value("Investigation Client",
                                      {"platform_user": user}, "name")
    if not client_name:
        frappe.local.flags.redirect_location = "/signup"
        raise frappe.Redirect

    c = frappe.get_doc("Investigation Client", client_name)
    if not c.onboarding_started_at:
        c.onboarding_started_at = frappe.utils.now_datetime()
        c.save(ignore_permissions=True)
        frappe.db.commit()

    status = c.onboarding_status or "Pending Email"
    is_individual = (c.client_type == "Individual")

    # Skip Pending Email if user already verified (login means verified)
    if status == "Pending Email":
        status = "Pending Card"
        frappe.db.set_value("Investigation Client", c.name,
                            "onboarding_status", "Pending Card")
        frappe.db.commit()

    # Route by status
    route_map = {
        "Pending Card":   "/onboarding/card",
        "Pending KYC":    "/onboarding/kyc",
        "Pending KYB":    "/onboarding/kyb",
    }
    if status in route_map:
        frappe.local.flags.redirect_location = route_map[status]
        raise frappe.Redirect

    # Under Review or Active
    context.client = c
    context.is_individual = is_individual
    context.status = status
