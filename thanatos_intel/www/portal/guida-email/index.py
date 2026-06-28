import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/guida-email"
        raise frappe.Redirect
    user = frappe.session.user
    # casella suggerita: se l'utente è già @thanatos.agency usala, altrimenti lascia placeholder
    mailbox = user if user.endswith("@thanatos.agency") else ""
    if not mailbox:
        # prova a trovare una casella collegata all'utente (Investigation Client / Contact)
        mailbox = frappe.db.get_value("Investigation Client", {"platform_user": user}, "email") or ""
    context.user_mailbox = mailbox
    context.title = "Guida configurazione email — Thanatos"
    return context
