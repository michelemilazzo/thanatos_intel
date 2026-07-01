"""Thanatos Switchboard (PWA Centralino) - context provider."""
import frappe

no_cache = 1
no_sitemap = 1


def get_context(context):
    context.no_cache = 1
    context.title = "Thanatos Switchboard"
    user = frappe.session.user
    if user == "Guest":
        context.logged_in = False
        context.next_url = "/ops/"
        return context
    roles = set(frappe.get_roles(user) or [])
    context.logged_in = True
    context.user = user
    context.user_name = frappe.db.get_value("User", user, "full_name") or user
    context.user_image = frappe.db.get_value("User", user, "user_image") or ""
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.is_operator = bool(roles & {"System Manager", "Investigation Manager",
                                        "Investigator"})
    context.is_admin = bool(roles & {"System Manager", "Investigation Manager"})
    context.is_super_admin = "System Manager" in roles
    # nome operatore Investigator (se esiste)
    inv = frappe.db.get_value("Investigator", {"platform_user": user},
                              ["name", "codename"], as_dict=True)
    context.investigator = inv.get("name") if inv else None
    context.investigator_codename = inv.get("codename") if inv else None
    if not context.is_operator:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
    return context
