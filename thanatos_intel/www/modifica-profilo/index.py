import frappe

no_cache = 1

_SUBMITTABLE = ("", "Not Required", "Not Started", "In Progress", "Failed", "Rejected", None)


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

	c = None
	cname = frappe.db.get_value(
		"Investigation Client", {"platform_user": frappe.session.user}, "name"
	)
	if cname:
		c = frappe.get_doc("Investigation Client", cname)
	context.has_client = bool(c)
	context.client_docname = c.name if c else ""

	def g(field, default=""):
		return (c.get(field) if c else "") or default

	context.client_name = g("client_name")
	context.client_type = g("client_type")
	context.vat_number = g("vat_number")
	context.codice_fiscale = g("codice_fiscale")
	context.preferred_language = g("preferred_language")
	context.country = g("country")

	# Indirizzi
	for pfx in ("res", "dom", "ship"):
		for suf in ("address_line1", "city", "province", "postal_code", "country"):
			setattr(context, f"{pfx}_{suf}", g(f"{pfx}_{suf}"))
	# flag default ON quando il cliente non ha ancora salvato nulla
	context.dom_same_as_res = 1 if (not c or c.get("dom_same_as_res")) else 0
	context.ship_same_as_res = 1 if (not c or c.get("ship_same_as_res")) else 0
	context.bill_same_as_res = 1 if (not c or c.get("bill_same_as_res")) else 0
	context.billing_address_line1 = g("billing_address_line1")
	context.billing_city = g("billing_city")
	context.billing_province = g("billing_province")
	context.billing_postal_code = g("billing_postal_code")

	try:
		context.countries = frappe.get_all("Country", pluck="name", order_by="name asc")
	except Exception:
		context.countries = []

	# Verifica identita (KYC privati / KYB aziende)
	context.is_individual = (context.client_type == "Individual") or not context.client_type
	context.kyc_status = g("kyc_status")
	context.kyb_status = g("kyb_status")
	cur_status = context.kyc_status if context.is_individual else context.kyb_status
	context.verify_status = cur_status or "Not Started"
	context.can_submit_verify = bool(c) and (cur_status in _SUBMITTABLE)

	# documenti gia inviati (allegati all'ultimo check)
	context.verify_docs = []
	if c:
		check_dt = "KYC Check" if context.is_individual else "KYB Check"
		last = frappe.get_all(check_dt, filters={"client": c.name},
		                      fields=["name"], order_by="creation desc", limit=1)
		if last:
			context.verify_docs = frappe.get_all("File",
				filters={"attached_to_doctype": check_dt, "attached_to_name": last[0].name},
				fields=["file_name", "file_url"], limit=20)

	context.no_cache = 1
	return context
