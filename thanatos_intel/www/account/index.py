import frappe

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/account"
		raise frappe.Redirect
	try:
		from thanatos_intel.permissions import is_full_access
		if is_full_access(frappe.session.user):
			frappe.local.flags.redirect_location = "/app"
			raise frappe.Redirect
	except frappe.Redirect:
		raise
	except Exception:
		pass
	u = frappe.get_doc("User", frappe.session.user)
	context.user_email = u.email
	context.full_name = u.full_name or u.email

	# Scheda cliente: tipo, KYC e (se societa') KYB
	cl = frappe.db.get_value(
		"Investigation Client",
		{"platform_user": frappe.session.user},
		["name", "client_type", "kyc_status", "kyb_status", "vat_number", "onboarding_status"],
		as_dict=True,
	)
	context.client = cl
	context.is_company = bool(cl and (cl.client_type or "") not in ("", "Individual"))
	context.no_cache = 1
	return context
