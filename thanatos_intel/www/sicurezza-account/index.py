import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/sicurezza-account"
		raise frappe.Redirect

	from mmos_brand.two_factor import OPTIN_ROLE

	context.user = frappe.session.user
	context.enabled = OPTIN_ROLE in frappe.get_roles(frappe.session.user)
	return context
