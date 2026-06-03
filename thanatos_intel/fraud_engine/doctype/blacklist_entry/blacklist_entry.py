import frappe
from frappe.model.document import Document
from frappe.utils import today


class BlacklistEntry(Document):
	def validate(self):
		# Normalizza: email/domain/IP/IBAN tutti lowercase + strip
		if self.entry_value:
			val = self.entry_value.strip()
			if self.entry_type in ("Email", "Domain", "IP", "Wallet", "IBAN"):
				val = val.lower()
			self.entry_value = val

	@staticmethod
	def check(value: str, entry_type: str = None) -> bool:
		"""Ritorna True se il valore è in blacklist attiva."""
		if not value:
			return False
		filters = {"entry_value": value.strip().lower() if entry_type in ("Email", "Domain", "IP", "Wallet", "IBAN") else value.strip(),
				   "is_active": 1}
		if entry_type:
			filters["entry_type"] = entry_type
		return bool(frappe.db.exists("Blacklist Entry", filters))

	@staticmethod
	def add_hit(value: str, entry_type: str = None):
		"""Incrementa occurrences + aggiorna last_seen."""
		if not value:
			return None
		val = value.strip().lower() if entry_type in ("Email", "Domain", "IP", "Wallet", "IBAN") else value.strip()
		filters = {"entry_value": val, "is_active": 1}
		if entry_type:
			filters["entry_type"] = entry_type
		name = frappe.db.get_value("Blacklist Entry", filters, "name")
		if not name:
			return None
		current = frappe.db.get_value("Blacklist Entry", name, "occurrences") or 0
		frappe.db.set_value("Blacklist Entry", name, {"occurrences": current + 1, "last_seen": today()}, update_modified=False)
		frappe.db.commit()
		return name
