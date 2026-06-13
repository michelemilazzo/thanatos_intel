import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import time_diff_in_seconds


class FieldActivity(Document):
	def validate(self):
		self._compute_duration()

	def before_submit(self):
		# Le attività con base giuridica sensibile devono dichiarare la liceità
		if self.activity_type in ("Pedinamento", "Chiamata") and not self.consent_confirmed:
			frappe.throw(
				_("Per attività di tipo {0} è obbligatorio confermare la liceità "
				  "(base giuridica) prima della registrazione definitiva.").format(self.activity_type)
			)

	def on_submit(self):
		# Materializza ogni allegato come reperto in catena di custodia
		for row in self.attachments:
			if row.file and not row.evidence_ref:
				self._create_evidence(row)

	def _compute_duration(self):
		if self.start_datetime and self.end_datetime:
			secs = time_diff_in_seconds(self.end_datetime, self.start_datetime)
			if secs < 0:
				frappe.throw(_("La fine non può precedere l'inizio."))
			self.duration_minutes = round(secs / 60.0, 1)
			self.billable_hours = round(secs / 3600.0, 2) if self.billable else 0.0
		else:
			self.duration_minutes = 0.0
			self.billable_hours = 0.0

	def _create_evidence(self, row):
		ev = frappe.get_doc({
			"doctype": "Investigation Evidence",
			"investigation_case": self.investigation_case,
			"evidence_name": row.caption or f"{self.activity_type} — {self.name}",
			"evidence_type": "Document",
			"attached_file": row.file,
			"acquisition_date": row.captured_at or self.start_datetime,
			"acquired_by": self.investigator,
			"source": f"Field Activity {self.name}",
		})
		ev.insert(ignore_permissions=True)
		row.db_set("evidence_ref", ev.name)
		row.db_set("sha256", ev.hash_value or "")

	@frappe.whitelist()
	def mark_verified(self):
		self.db_set("verified", 1)
		self.db_set("verified_by", frappe.session.user)
		return {"ok": True}
