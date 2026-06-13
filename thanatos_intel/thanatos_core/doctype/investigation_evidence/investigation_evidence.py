import hashlib
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class InvestigationEvidence(Document):
	def before_save(self):
		# Forza il File allegato a is_private=1 e calcola SHA-256 se mancante
		if self.attached_file:
			self._force_private_and_hash()
		if self.hash_value:
			self.hash_value = self.hash_value.strip().lower()

	def after_insert(self):
		self._append_custody_log("Created", "Evidence acquisita")

	def on_update(self):
		# Se cambia il file, aggiorna hash e logga Modified
		if self.has_value_changed("attached_file") and self.attached_file:
			self._force_private_and_hash()
			self._append_custody_log("Modified", "File aggiornato")

	def on_trash(self):
		# Catena di custodia (Cod procedură penală (Legea 135/2010)): le prove NON si cancellano.
		# Solo archive_evidence() può flaggare archived=1 senza distruggere.
		frappe.throw(
			_("Le prove non possono essere eliminate (catena di custodia ex Cod procedură penală (Legea 135/2010)). "
			  "Usare il comando 'Archive' per marcare la prova come archiviata."),
			frappe.PermissionError,
		)

	@frappe.whitelist()
	def archive_evidence(self, reason: str = ""):
		self.archived = 1
		self.custody_status = "Archived"
		self.save(ignore_permissions=False)
		self._append_custody_log("Archived", f"Archived: {reason or 'no reason given'}")
		return {"ok": True}

	# --- private helpers ---

	def _force_private_and_hash(self):
		try:
			file_doc = frappe.get_doc("File", {"file_url": self.attached_file})
			# Forza is_private
			if not file_doc.is_private:
				file_doc.is_private = 1
				file_doc.save(ignore_permissions=True)
			# Calcola SHA-256 dal contenuto effettivo
			content = file_doc.get_content()
			if isinstance(content, str):
				content = content.encode("utf-8", errors="ignore")
			if content:
				h = hashlib.sha256(content).hexdigest()
				if h != (self.hash_value or "").lower():
					self.hash_value = h
		except Exception:
			# Best-effort: non blocca il save se il File non è leggibile
			frappe.log_error(frappe.get_traceback(), "InvestigationEvidence hash")

	def _append_custody_log(self, operation: str, note: str):
		try:
			row = frappe.get_doc({
				"doctype": "Custody Log Entry",
				"parent": self.name,
				"parenttype": "Investigation Evidence",
				"parentfield": "custody_log",
				"timestamp": now_datetime(),
				"operation": operation,
				"operator": frappe.session.user,
				"note": note[:140] if note else "",
				"hash_at_time": self.hash_value or "",
			})
			row.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "InvestigationEvidence custody_log")
