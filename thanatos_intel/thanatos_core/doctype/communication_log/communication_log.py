import hashlib
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class CommunicationLog(Document):
	def before_save(self):
		if self.attachment:
			self._hash_attachment()

	def _hash_attachment(self):
		try:
			file_doc = frappe.get_doc("File", {"file_url": self.attachment})
			if not file_doc.is_private:
				file_doc.is_private = 1
				file_doc.save(ignore_permissions=True)
			content = file_doc.get_content()
			if isinstance(content, str):
				content = content.encode("utf-8", errors="ignore")
			if content:
				self.sha256 = hashlib.sha256(content).hexdigest()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "CommunicationLog hash")

	@frappe.whitelist()
	def promote_to_evidence(self):
		"""Crea un reperto in catena di custodia dall'allegato della comunicazione."""
		if not self.attachment:
			frappe.throw("Nessun allegato da promuovere a reperto.")
		if self.evidence_ref:
			return {"ok": True, "evidence": self.evidence_ref}
		ev = frappe.get_doc({
			"doctype": "Investigation Evidence",
			"investigation_case": self.investigation_case,
			"evidence_name": f"{self.channel} {self.direction} — {self.counterparty_name or self.name}",
			"evidence_type": "Document",
			"attached_file": self.attachment,
			"acquisition_date": self.occurred_at or now_datetime(),
			"acquired_by": self.investigator,
			"source": f"Communication Log {self.name}",
		})
		ev.insert(ignore_permissions=True)
		self.db_set("evidence_ref", ev.name)
		self.db_set("sha256", ev.hash_value or "")
		return {"ok": True, "evidence": ev.name}
