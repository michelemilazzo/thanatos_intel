import frappe


no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal"
        raise frappe.Redirect
    context.session_id = frappe.form_dict.get("session_id")
    context.title = "Pagamento confermato — Thanatos Intel"
    return context
