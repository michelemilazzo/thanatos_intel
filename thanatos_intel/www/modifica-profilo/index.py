import frappe

no_cache = 1

_SUBMITTABLE = ("", "Not Required", "Not Started", "In Progress", "Failed", "Rejected", None)


def _docs_for(check_dt, client):
	last = frappe.get_all(check_dt, filters={"client": client},
	                      fields=["name"], order_by="creation desc", limit=1)
	if not last:
		return []
	return frappe.get_all("File",
		filters={"attached_to_doctype": check_dt, "attached_to_name": last[0].name},
		fields=["file_name", "file_url"], limit=20)


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

	for pfx in ("res", "dom", "ship"):
		for suf in ("address_line1", "city", "province", "postal_code", "country"):
			setattr(context, f"{pfx}_{suf}", g(f"{pfx}_{suf}"))
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

	# Verifica
	context.is_individual = (context.client_type == "Individual") or not context.client_type
	context.has_company = 1 if (c and c.get("has_company")) else 0
	context.company_role = g("company_role")

	context.kyc_status = g("kyc_status") or "Not Started"
	context.kyb_status = g("kyb_status") or "Not Started"
	context.kyc_can_submit = bool(c) and (g("kyc_status") in _SUBMITTABLE)
	context.kyb_can_submit = bool(c) and (g("kyb_status") in _SUBMITTABLE)
	context.kyc_docs = _docs_for("KYC Check", c.name) if c else []
	context.kyb_docs = _docs_for("KYB Check", c.name) if c else []
	# il KYB serve alle aziende sempre, e ai privati solo se has_company
	context.kyb_required = bool(c) and ((not context.is_individual) or context.has_company)

	# Segnalazione clienti (referral)
	context.ref = {}
	if c:
		try:
			from thanatos_intel import referral
			context.ref = referral.my_tree(frappe.session.user) or {}
		except Exception:
			context.ref = {}
	context.ref_qr = None
	link = (context.ref or {}).get("link")
	if link:
		try:
			import io, base64, qrcode
			img = qrcode.make(link)
			buf = io.BytesIO(); img.save(buf, format="PNG")
			context.ref_qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
		except Exception:
			context.ref_qr = None

	context.no_cache = 1
	return context
