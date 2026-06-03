# Copyright (c) 2026, OneKeyCo

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today


class InvestigationCase(Document):
	def before_insert(self):
		# Auto-numbering CASE-YYYY-NNNN per anno
		if not self.case_number:
			self.case_number = generate_case_number()

	def validate(self):
		if self.case_title:
			self.case_title = self.case_title.strip()
		if not self.status:
			self.status = "Draft"

	def after_insert(self):
		# Log iniziale come Case Activity
		self.append("case_activities", {
			"activity_date": now_datetime(),
			"activity_type": "Report",
			"description": f"Caso aperto da {frappe.session.user}",
			"operator": frappe.session.user,
			"hours_spent": 0,
		})
		self.db_update()
		# Drive folder per il caso (best-effort, async-safe)
		try:
			from thanatos_intel.integrations.drive_bridge import ensure_case_folder
			ensure_case_folder(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"InvestigationCase.after_insert drive {self.name}")

	def on_update(self):
		# Se status passa a Closed, valorizza closing_date e aggiorna stats client
		if self.status == "Closed" and not self.closing_date:
			self.db_set("closing_date", today(), update_modified=False)
		if self.client:
			n = frappe.db.count("Investigation Case", {"client": self.client})
			frappe.db.set_value("Investigation Client", self.client, "total_cases", n)


def generate_case_number() -> str:
	from datetime import datetime
	year = datetime.now().year
	prefix = f"CASE-{year}-"
	last = frappe.db.sql(
		"SELECT case_number FROM `tabInvestigation Case` WHERE case_number LIKE %s ORDER BY case_number DESC LIMIT 1",
		(prefix + "%",),
	)
	if last:
		try:
			n = int(last[0][0].split("-")[-1])
		except Exception:
			n = 0
	else:
		n = 0
	return f"{prefix}{(n + 1):04d}"
