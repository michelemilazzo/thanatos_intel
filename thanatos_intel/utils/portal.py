import frappe

PORTAL_ROLES = {"Investigation Client", "Affiliate", "Investigator", "Investigation Manager"}
DESK_ROLES = {"System Manager", "Investigation Manager"}


def get_home_page(user=None):
    user = user or frappe.session.user
    if user in ("Guest", ""):
        return "home"
    roles = set(frappe.get_roles(user))
    if roles & DESK_ROLES:
        return "/app"
    if roles & PORTAL_ROLES:
        return "/portal"
    return "/portal"
