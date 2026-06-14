import frappe
from frappe import _
from frappe.model.document import Document


class TrackedAsset(Document):
	def validate(self):
		# Gating legale: nessun tracciamento attivo senza base giuridica + documento
		if self.active:
			if not self.legal_basis:
				frappe.throw(_("Impossibile attivare il tracciamento senza una base giuridica (Legea 329/2003)."))
			if not self.consent_document:
				frappe.throw(_("Impossibile attivare il tracciamento senza il documento di consenso/mandato allegato."))

	def before_insert(self):
		if not self.ingest_token:
			self.ingest_token = frappe.generate_hash(length=40)

	@frappe.whitelist()
	def activate(self):
		if not self.legal_basis or not self.consent_document:
			frappe.throw(_("Base giuridica e documento di consenso obbligatori prima dell'attivazione."))
		self.db_set("active", 1)
		self._custody_event("Created", f"Tracciamento attivato — base: {self.legal_basis}")
		return {"ok": True}

	@frappe.whitelist()
	def deactivate(self, reason: str = ""):
		self.db_set("active", 0)
		self._custody_event("Modified", f"Tracciamento disattivato — {reason or 'no reason'}")
		return {"ok": True}

	def _custody_event(self, event_type: str, notes: str):
		try:
			frappe.get_doc({
				"doctype": "Chain of Custody Event",
				"event_type": event_type,
				"related_reference": self.name,
				"notes": notes[:140],
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "TrackedAsset custody event")

	def is_within_window(self) -> bool:
		from frappe.utils import getdate, nowdate
		today = getdate(nowdate())
		if self.authorized_from and getdate(self.authorized_from) > today:
			return False
		if self.authorized_to and getdate(self.authorized_to) < today:
			return False
		return True
