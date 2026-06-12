import frappe
from frappe import _

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/billing"
        raise frappe.Redirect

    user = frappe.session.user
    client_name = frappe.db.get_value("Investigation Client", {"platform_user": user}, "name")
    context.client = frappe.get_doc("Investigation Client", client_name) if client_name else None

    context.is_credit = bool(getattr(context.client, "credit_granted", 0)) if context.client else False
    context.payment_method = getattr(context.client, "payment_method", None) if context.client else None
    if client_name:
        from thanatos_intel.billing.credits import available_to_spend
        context.available = available_to_spend(client_name)
        context.active_addons = [a.strip() for a in
                                 (getattr(context.client, "active_addons", "") or "").split(",") if a.strip()]
    else:
        context.available = 0
        context.active_addons = []

    context.plans = frappe.get_all(
        "Investigation Subscription Plan",
        filters={"is_active": 1},
        fields=["name", "plan_name", "plan_level", "monthly_price", "currency",
                "included_verifications", "included_analyses", "included_reports",
                "max_users", "support_level", "description"],
        order_by="monthly_price asc",
    )

    from thanatos_intel.integrations.stripe_bridge import ADDON_SERVICE_CODES
    context.addons = frappe.get_all(
        "Service Catalog",
        filters={"service_code": ["in", ADDON_SERVICE_CODES], "is_active": 1},
        fields=["service_code", "service_name", "price", "currency", "description"],
        order_by="price asc",
    )

    context.current_sub = None
    if client_name:
        subs = frappe.get_all(
            "Stripe Subscription",
            filters={"investigation_client": client_name,
                     "status": ["in", ["active", "trialing", "past_due"]]},
            fields=["name", "stripe_subscription_id", "subscription_plan", "status",
                    "amount", "currency", "current_period_end"],
            order_by="creation desc",
            limit=1,
        )
        context.current_sub = subs[0] if subs else None

    context.requested_service = None
    svc = frappe.form_dict.get("svc")
    if svc:
        row = frappe.db.get_value("Service Catalog", {"service_code": svc, "is_active": 1},
                                  ["service_code", "service_name", "category", "price", "currency"],
                                  as_dict=True)
        context.requested_service = row

    context.stripe_configured = bool(frappe.conf.get("stripe_secret_key"))
    context.stripe_publishable_key = frappe.conf.get("stripe_publishable_key") or ""
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = frappe.local.session.get("csrf_token") if frappe.local.session else ""
    context.title = "Billing — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
