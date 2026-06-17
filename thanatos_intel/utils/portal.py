import frappe

PORTAL_ROLES = {"Investigation Client", "Affiliate", "Investigator", "Investigation Manager"}
DESK_ROLES = {"System Manager", "Investigation Manager"}


def get_home_page(user=None):
    user = user or frappe.session.user
    if user in ("Guest", ""):
        return "home"
    roles = set(frappe.get_roles(user))
    if roles & DESK_ROLES:
        return "/app/thanatos-intel"
    if roles & PORTAL_ROLES:
        return "/portal"
    return "/portal"


def add_csrf_token(context):
	"""Inietta il csrf_token per gli utenti loggati su OGNI pagina website
	(evita 'Invalid Request' nelle pagine che fanno POST senza settarlo a mano)."""
	import frappe
	user = getattr(frappe.session, "user", None)
	if user and user != "Guest":
		from frappe.sessions import get_csrf_token
		context.csrf_token = get_csrf_token()
