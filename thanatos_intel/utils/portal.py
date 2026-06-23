import frappe

PORTAL_ROLES = {"Investigation Client", "Affiliate", "Investigator", "Investigation Manager"}
DESK_ROLES = {"System Manager", "Investigation Manager", "Investigator",
              "Thanatos Investigator", "Thanatos Supervisor", "Thanatos Director",
              "Thanatos Analyst", "Analyst", "Thanatos Intake Officer",
              "Thanatos Legal Officer", "Thanatos Compliance Officer"}


def get_home_page(user=None):
    user = user or frappe.session.user
    if user in ("Guest", ""):
        return "home"
    roles = set(frappe.get_roles(user))
    if roles & DESK_ROLES:
        # la home pubblica "/" deve renderizzare una rotta website valida:
        # un percorso /app/* non e' servibile come home e darebbe 404.
        # Lo staff entra nel desk dal menu utente (App Thanatos / Desk).
        return "home"
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


def confine_client_session(login_manager=None):
    """on_session_creation: i clienti (e ruoli portale) restano sempre nel portale.
    Anche se hanno un ruolo desk spurio (es. Wiki User), il redirect post-login va a
    /portal. Lo staff vero (DESK_ROLES) va al desk."""
    user = getattr(frappe.session, "user", None)
    if not user or user == "Guest":
        return
    roles = set(frappe.get_roles(user))
    if roles & DESK_ROLES:
        return
    if roles & PORTAL_ROLES:
        frappe.local.response["home_page"] = "/portal"


def bounce_client_from_desk():
    """before_request: un cliente (ruolo portale, non staff) non deve MAI vedere il
    desk. Qualsiasi richiesta a /app viene rimandata a /portal. I System User hanno
    il ruolo intrinseco 'Desk User' (desk_access=1), quindi la confinazione si fa qui."""
    try:
        path = (frappe.local.request.path or "")
    except Exception:
        return
    if not (path == "/app" or path.startswith("/app/") or path.startswith("/app?")):
        return
    user = getattr(frappe.session, "user", None)
    if not user or user == "Guest":
        return
    roles = set(frappe.get_roles(user))
    if roles & DESK_ROLES:
        return
    if roles & PORTAL_ROLES:
        frappe.local.flags.redirect_location = "/portal"
        raise frappe.Redirect
