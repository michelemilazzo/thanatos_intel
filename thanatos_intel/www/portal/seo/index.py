import frappe

no_cache = 1


def get_context(context):
    # SEO & Analytics è una funzione staff: vive nel desk (/app/seo-analytics).
    # Questa rotta legacy reindirizza lì.
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/app/seo-analytics"
    else:
        frappe.local.flags.redirect_location = "/app/seo-analytics"
    raise frappe.Redirect
