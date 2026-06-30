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
		self._sync_territory()
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
		if not emp:
			emp = self._maybe_create_employee()
		if not emp:
			return
		self.erp_employee_id = emp
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

	def _maybe_create_employee(self):
		"""Crea automaticamente l'Employee ERPNext (HR) se manca. Best-effort: se i
		dati obbligatori non bastano, salta senza rompere il salvataggio."""
		if not self.platform_user:
			return None
		dob = None
		if self.soggetto:
			dob = frappe.db.get_value("Soggetto", self.soggetto, "data_nascita")
		if not dob:
			return None  # DOB obbligatorio in ERPNext: senza, non creiamo (no invenzioni)
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not company:
			return None
		gender = (frappe.db.get_value("Gender", {"name": ["in", ["Prefer not to say", "Other"]]}, "name")
		          or frappe.db.get_value("Gender", {}, "name"))
		fn = (self.full_name or self.platform_user or "").strip()
		try:
			e = frappe.get_doc({
				"doctype": "Employee",
				"first_name": fn.split(" ")[0] or fn,
				"last_name": " ".join(fn.split(" ")[1:]),
				"employee_name": fn,
				"company": company,
				"gender": gender,
				"date_of_birth": dob,
				"date_of_joining": frappe.utils.today(),
				"status": "Active",
				"user_id": self.platform_user,
				"cell_number": self.phone,
			})
			e.flags.ignore_permissions = True
			e.insert(ignore_permissions=True)
			frappe.db.commit()
			return e.name
		except Exception:
			frappe.log_error(frappe.get_traceback(), "auto-create Employee")
			return None

	def _sync_territory(self):
		"""Auto-compila il Territory dall'indirizzo predefinito del Soggetto."""
		if (self.territory or "").strip() or not self.soggetto:
			return
		addr = frappe.db.get_value("Soggetto Indirizzo",
			{"parent": self.soggetto, "is_default": 1},
			["provincia", "citta", "nazione"], as_dict=True)
		if addr:
			self.territory = (addr.provincia or addr.citta or addr.nazione or "").strip()


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


def check_license_expiry():
    """Giornaliero: avvisa i manager quando l'atestat/licenza di un investigatore
    scade entro 30 giorni (Legea 329/2003)."""
    from frappe.utils import nowdate, add_days, date_diff, getdate
    soon = add_days(nowdate(), 30)
    rows = frappe.get_all("Investigator",
        filters={"license_expiry": ["between", [nowdate(), soon]]},
        fields=["name", "codename", "license_expiry"])
    if not rows:
        return
    managers = frappe.get_all("Has Role",
        filters={"role": ["in", ["Investigation Manager", "System Manager"]]},
        pluck="parent")
    managers = [m for m in set(managers) if m not in ("Guest", "Administrator")] or ["Administrator"]
    for r in rows:
        days = date_diff(getdate(r.license_expiry), getdate(nowdate()))
        title = "Licenza investigatore in scadenza"
        msg = "%s (%s): licenza/atestat scade il %s (tra %d giorni)." % (
            r.name, r.codename or "", r.license_expiry, days)
        for u in managers:
            try:
                frappe.get_doc({"doctype": "Notification Log", "subject": title,
                    "email_content": msg, "for_user": u, "type": "Alert",
                    "document_type": "Investigator", "document_name": r.name,
                    "from_user": "Administrator"}).insert(ignore_permissions=True)
            except Exception:
                pass
    frappe.db.commit()
