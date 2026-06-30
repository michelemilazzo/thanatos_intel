"""Thanatos Switchboard (PWA Centralino) - context provider."""
import frappe
from frappe import _

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
    context.is_operator = bool(roles & {"System Manager", "Investigation Manager",
                                        "Investigator"})
    if not context.is_operator:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
    return context
