import frappe


def get_context(context):
    context.no_cache = 1
    context.title = "Video Identification — Thanatos DDD"
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/ddd/video"
        raise frappe.Redirect
    context.case = frappe.form_dict.get("case", "")
    return context
