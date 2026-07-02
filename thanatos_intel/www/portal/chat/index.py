"""Portal chat cliente: chat web con l'operatore Thanatos, staccata da WhatsApp.
Sicurezza: solo casi visibili all'utente loggato."""
import frappe

no_cache = 1


def get_context(context):
    user = frappe.session.user
    if user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=%2Fportal%2Fchat"
        raise frappe.Redirect
    from thanatos_intel.permissions import visible_case_names
    context.title = "Chat con Thanatos"
    context.user = user
    context.user_name = frappe.db.get_value("User", user, "full_name") or user
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.case_names = visible_case_names(user) or []
    return context
