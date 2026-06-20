import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/modifica-profilo"
		raise frappe.Redirect
	u = frappe.get_doc("User", frappe.session.user)
	context.user_email = u.email
	context.first_name = u.first_name or ""
	context.last_name = u.last_name or ""
	context.phone = u.phone or ""
	context.mobile_no = u.mobile_no or ""
	context.no_cache = 1
	return context
