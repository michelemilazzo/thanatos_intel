import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/guida-email"
        raise frappe.Redirect
    user = frappe.session.user
    context.user_mailbox = user if str(user).endswith("@thanatos.agency") else ""
    context.title = "Guida configurazione email — Thanatos"
    return context
