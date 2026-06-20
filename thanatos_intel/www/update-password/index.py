import frappe

no_cache = 1


def get_context(context):
	key = frappe.form_dict.get("key") or ""
	# Guest allowed only via reset-key flow (email link); otherwise must log in
	if frappe.session.user == "Guest" and not key:
		frappe.local.flags.redirect_location = "/login?redirect-to=/update-password"
		raise frappe.Redirect
	context.key = key
	context.no_cache = 1
	return context
