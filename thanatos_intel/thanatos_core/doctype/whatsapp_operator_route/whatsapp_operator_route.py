import frappe
from frappe.model.document import Document


class WhatsAppOperatorRoute(Document):
	def validate(self):
		if self.investigator and not (self.phone or "").strip():
			self.phone = frappe.db.get_value("Investigator", self.investigator, "phone")
