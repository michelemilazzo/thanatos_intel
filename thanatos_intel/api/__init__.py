import frappe


@frappe.whitelist()
def update_my_profile(first_name=None, last_name=None, phone=None, mobile_no=None,
                      client_name=None, client_type=None, country=None,
                      vat_number=None, codice_fiscale=None, preferred_language=None,
                      billing_address_line1=None, billing_city=None,
                      billing_province=None, billing_postal_code=None):
	"""Aggiorna i dati anagrafici/contatto dell'utente corrente (portale) e,
	se esiste, l'anagrafica/fatturazione del suo Investigation Client."""
	if frappe.session.user == "Guest":
		frappe.throw("Accesso richiesto", frappe.PermissionError)
	u = frappe.get_doc("User", frappe.session.user)
	for field, value in {
		"first_name": first_name,
		"last_name": last_name,
		"phone": phone,
		"mobile_no": mobile_no,
	}.items():
		if value is not None:
			u.set(field, value.strip())
	u.save(ignore_permissions=True)

	# Dati cliente: solo il record collegato all'utente corrente
	cname = frappe.db.get_value(
		"Investigation Client", {"platform_user": frappe.session.user}, "name"
	)
	if cname:
		c = frappe.get_doc("Investigation Client", cname)
		changed = False
		for field, value in {
			"client_name": client_name,
			"client_type": client_type,
			"country": country,
			"vat_number": vat_number,
			"codice_fiscale": codice_fiscale,
			"preferred_language": preferred_language,
			"billing_address_line1": billing_address_line1,
			"billing_city": billing_city,
			"billing_province": billing_province,
			"billing_postal_code": billing_postal_code,
		}.items():
			if value is not None:
				c.set(field, value.strip() if isinstance(value, str) else value)
				changed = True
		if changed:
			c.save(ignore_permissions=True)
	frappe.db.commit()
	return {"full_name": u.full_name or u.email}
