import frappe
from frappe.model.document import Document


class Investigator(Document):
	def before_insert(self):
		if not (self.codename or "").strip():
			self.codename = _next_codename()

	def validate(self):
		if self.codename:
			self.codename = self.codename.strip()
		self._sync_user()
		self._sync_employee()
		self._refresh_active_cases()

	def _sync_user(self):
		"""Auto-compila nome/telefono dall'utente piattaforma collegato."""
		if not self.platform_user:
			return
		u = frappe.db.get_value("User", self.platform_user,
			["full_name", "phone", "mobile_no"], as_dict=True)
		if not u:
			return
		if not (self.full_name or "").strip() and u.full_name:
			self.full_name = u.full_name
		if not (self.phone or "").strip():
			self.phone = (u.mobile_no or u.phone or "").strip()

	def _sync_employee(self):
		"""Collega e sincronizza con l'Employee ERPNext (HR) dello stesso utente."""
		emp = self.erp_employee_id
		if not emp and self.platform_user:
			emp = frappe.db.get_value("Employee", {"user_id": self.platform_user}, "name")
			if emp:
				self.erp_employee_id = emp
		if not emp:
			return
		ed = frappe.db.get_value("Employee", emp, ["employee_name", "cell_number"], as_dict=True)
		if not ed:
			return
		if not (self.full_name or "").strip() and ed.employee_name:
			self.full_name = ed.employee_name
		if not (self.phone or "").strip() and ed.cell_number:
			self.phone = ed.cell_number
		# push telefono verso HR se mancante lì
		if (self.phone or "").strip() and not (ed.cell_number or "").strip():
			try:
				frappe.db.set_value("Employee", emp, "cell_number", self.phone, update_modified=False)
			except Exception:
				pass

	def _refresh_active_cases(self):
		if not self.name:
			return
		try:
			rows = frappe.db.sql(
				"""SELECT COUNT(DISTINCT ca.parent) FROM `tabCase Assignment` ca
				   WHERE ca.assignee=%s AND ca.parenttype='Investigation Case'""",
				(self.name,))
			self.active_cases_count = int(rows[0][0]) if rows and rows[0][0] else 0
		except Exception:
			pass


@frappe.whitelist()
def refresh_active_cases(investigator):
	"""Ricalcola e salva il conteggio casi attivi dell'investigatore."""
	doc = frappe.get_doc("Investigator", investigator)
	doc._refresh_active_cases()
	doc.db_set("active_cases_count", doc.active_cases_count, update_modified=False)
	return doc.active_cases_count


def on_case_update(doc, method=None):
	"""Hook Investigation Case: aggiorna il conteggio casi degli investigatori assegnati."""
	try:
		assignees = frappe.db.sql_list(
			"""SELECT DISTINCT assignee FROM `tabCase Assignment`
			   WHERE parent=%s AND parenttype='Investigation Case'
			     AND assignee IS NOT NULL AND assignee!=''""", (doc.name,))
		for inv in assignees:
			if frappe.db.exists("Investigator", inv):
				refresh_active_cases(inv)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "investigator on_case_update")


def _next_codename():
	rows = frappe.get_all("Investigator", filters={"codename": ["like", "INV-%"]},
	                      pluck="codename")
	mx = 0
	for c in rows:
		try:
			n = int(str(c).split("-", 1)[1])
			mx = max(mx, n)
		except Exception:
			pass
	n = mx + 1
	code = f"INV-{n:02d}"
	while frappe.db.exists("Investigator", {"codename": code}):
		n += 1
		code = f"INV-{n:02d}"
	return code


def external_name(investigator):
	"""Nome da mostrare a clienti/esterni: codename se presente, mai il nome reale."""
	if not investigator:
		return ""
	code = frappe.db.get_value("Investigator", investigator, "codename")
	return code or "Investigatore Thanatos"
