import frappe
import frappe.sessions

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/compiti"
        raise frappe.Redirect

    from thanatos_intel.workflow.api import my_tasks
    context.tasks = my_tasks()
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.title = "I miei compiti — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
