import frappe


@frappe.whitelist()
def update_my_profile(first_name=None, last_name=None, phone=None, mobile_no=None,
                      client_name=None, client_type=None, country=None,
                      vat_number=None, codice_fiscale=None, preferred_language=None,
                      res_address_line1=None, res_city=None, res_province=None,
                      res_postal_code=None, res_country=None,
                      dom_same_as_res=None, dom_address_line1=None, dom_city=None,
                      dom_province=None, dom_postal_code=None, dom_country=None,
                      ship_same_as_res=None, ship_address_line1=None, ship_city=None,
                      ship_province=None, ship_postal_code=None, ship_country=None,
                      bill_same_as_res=None, billing_address_line1=None,
                      billing_city=None, billing_province=None, billing_postal_code=None,
                      has_company=None, company_role=None):
	"""Aggiorna i dati dell'utente corrente (portale) e, se esiste, anagrafica,
	indirizzi (residenza/domicilio/spedizione/fatturazione) e fatturazione del suo
	Investigation Client. Gli indirizzi 'uguale a residenza' vengono copiati."""
	if frappe.session.user == "Guest":
		frappe.throw("Accesso richiesto", frappe.PermissionError)

	u = frappe.get_doc("User", frappe.session.user)
	for field, value in {
		"first_name": first_name, "last_name": last_name,
		"phone": phone, "mobile_no": mobile_no,
	}.items():
		if value is not None:
			u.set(field, value.strip())
	u.save(ignore_permissions=True)

	cname = frappe.db.get_value(
		"Investigation Client", {"platform_user": frappe.session.user}, "name"
	)
	if cname:
		c = frappe.get_doc("Investigation Client", cname)
		incoming = {
			"client_name": client_name, "client_type": client_type,
			"country": country, "vat_number": vat_number,
			"codice_fiscale": codice_fiscale, "preferred_language": preferred_language,
			"res_address_line1": res_address_line1, "res_city": res_city,
			"res_province": res_province, "res_postal_code": res_postal_code,
			"res_country": res_country,
			"dom_same_as_res": dom_same_as_res, "dom_address_line1": dom_address_line1,
			"dom_city": dom_city, "dom_province": dom_province,
			"dom_postal_code": dom_postal_code, "dom_country": dom_country,
			"ship_same_as_res": ship_same_as_res, "ship_address_line1": ship_address_line1,
			"ship_city": ship_city, "ship_province": ship_province,
			"ship_postal_code": ship_postal_code, "ship_country": ship_country,
			"bill_same_as_res": bill_same_as_res,
			"billing_address_line1": billing_address_line1, "billing_city": billing_city,
			"billing_province": billing_province, "billing_postal_code": billing_postal_code,
			"has_company": has_company, "company_role": company_role,
		}
		changed = False
		for field, value in incoming.items():
			if value is not None:
				if field.endswith("same_as_res") or field == "has_company":
					c.set(field, 1 if _truthy(value) else 0)
				else:
					c.set(field, value.strip() if isinstance(value, str) else value)
				changed = True

		# Copia indirizzi marcati "uguale a residenza"
		if _truthy(c.get("dom_same_as_res")) and c.res_address_line1:
			c.dom_address_line1 = c.res_address_line1
			c.dom_city = c.res_city
			c.dom_province = c.res_province
			c.dom_postal_code = c.res_postal_code
			c.dom_country = c.res_country
		if _truthy(c.get("ship_same_as_res")) and c.res_address_line1:
			c.ship_address_line1 = c.res_address_line1
			c.ship_city = c.res_city
			c.ship_province = c.res_province
			c.ship_postal_code = c.res_postal_code
			c.ship_country = c.res_country
		if _truthy(c.get("bill_same_as_res")) and c.res_address_line1:
			c.billing_address_line1 = c.res_address_line1
			c.billing_city = c.res_city
			c.billing_province = c.res_province
			c.billing_postal_code = c.res_postal_code
			c.country = c.res_country

		if changed:
			c.save(ignore_permissions=True)
	frappe.db.commit()
	return {"full_name": u.full_name or u.email}


def _truthy(v):
	return str(v).strip().lower() in ("1", "true", "on", "yes")
