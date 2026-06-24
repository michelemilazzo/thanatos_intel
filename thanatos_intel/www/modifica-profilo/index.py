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

	# Anagrafica/fatturazione dal record Investigation Client dell'utente
	c = None
	cname = frappe.db.get_value(
		"Investigation Client", {"platform_user": frappe.session.user}, "name"
	)
	if cname:
		c = frappe.get_doc("Investigation Client", cname)
	context.has_client = bool(c)
	context.client_name = (c.client_name if c else "") or ""
	context.client_type = (c.client_type if c else "") or ""
	context.country = (c.country if c else "") or ""
	context.vat_number = (c.vat_number if c else "") or ""
	context.codice_fiscale = (c.codice_fiscale if c else "") or ""
	context.preferred_language = (c.preferred_language if c else "") or ""
	context.billing_address_line1 = (c.billing_address_line1 if c else "") or ""
	context.billing_city = (c.billing_city if c else "") or ""
	context.billing_province = (c.billing_province if c else "") or ""
	context.billing_postal_code = (c.billing_postal_code if c else "") or ""

	try:
		context.countries = frappe.get_all("Country", pluck="name", order_by="name asc")
	except Exception:
		context.countries = []

	context.no_cache = 1
	return context
