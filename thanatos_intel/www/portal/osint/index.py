import frappe


no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/osint"
        raise frappe.Redirect

    user = frappe.session.user
    roles = set(frappe.get_roles(user))
    context.user = user
    context.user_fullname = frappe.db.get_value("User", user, "full_name") or user
    context.can_run_deep = bool(roles & {"Investigator", "Investigation Manager",
                                          "Lawyer", "Accountant", "System Manager"})

    context.recent_jobs = []
    try:
        if frappe.db.exists("DocType", "OSINT Job"):
            context.recent_jobs = frappe.get_all(
                "OSINT Job", fields=["name", "title", "target_type", "target_value",
                                     "mode", "status", "risk_score", "risk_band",
                                     "summary", "creation"],
                order_by="creation desc", limit=15)
    except Exception:
        pass

    context.title = "OSINT Console — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
