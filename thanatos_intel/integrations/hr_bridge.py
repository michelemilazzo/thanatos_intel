"""Bridge HR: Investigator ↔ Employee + Investigator Specialization → Employee Skill."""
import frappe


@frappe.whitelist()
def link_investigator_to_employee(investigator_name: str, employee_id: str | None = None) -> dict:
	"""Linka un Investigator a un Employee ERPNext HR.

	- Se employee_id passato: aggiorna il link
	- Altrimenti: cerca per email/nome dell'investigator
	- Crea Employee se mancante (solo per Type=Employee)
	"""
	inv = frappe.get_doc("Investigator", investigator_name)
	emp_name = employee_id or inv.erp_employee_id

	# Match per nome (best-effort)
	if not emp_name:
		emp_name = frappe.db.get_value("Employee", {"employee_name": inv.full_name}, "name")

	# Crea Employee se non trovato e tipo Employee
	if not emp_name and inv.investigator_type == "Employee":
		# Split full_name in first/last
		parts = (inv.full_name or "").split(maxsplit=1)
		first = parts[0] if parts else inv.full_name or "Investigator"
		last = parts[1] if len(parts) > 1 else ""

		emp = frappe.get_doc({
			"doctype": "Employee",
			"first_name": first,
			"last_name": last,
			"employee_name": inv.full_name,
			"company": _default_company(),
			"date_of_joining": frappe.utils.today(),
			"gender": "Other",  # placeholder, lo editi tu
			"date_of_birth": "1980-01-01",  # placeholder
			"status": "Active",
		}).insert(ignore_permissions=True)
		emp_name = emp.name

	if emp_name:
		frappe.db.set_value("Investigator", investigator_name, "erp_employee_id", emp_name)
		frappe.db.commit()
		return {"ok": True, "employee": emp_name, "investigator": investigator_name}
	return {"ok": False, "reason": "No employee match and investigator_type != Employee"}


def _default_company() -> str | None:
	c = frappe.db.get_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if not c:
		c = frappe.db.get_value("Company", {}, "name")
	return c
