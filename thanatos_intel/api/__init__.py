import frappe


@frappe.whitelist()
def update_my_profile(first_name=None, last_name=None, phone=None, mobile_no=None):
	"""Aggiorna i dati anagrafici/contatto dell'utente corrente (portale)."""
	if frappe.session.user == "Guest":
		frappe.throw("Accesso richiesto", frappe.PermissionError)
	u = frappe.get_doc("User", frappe.session.user)
	values = {
		"first_name": first_name,
		"last_name": last_name,
		"phone": phone,
		"mobile_no": mobile_no,
	}
	for field, value in values.items():
		if value is not None:
			u.set(field, value.strip())
	u.save(ignore_permissions=True)
	frappe.db.commit()
	return {"full_name": u.full_name or u.email}
