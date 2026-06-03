import frappe
from frappe.model.document import Document


class InvestigationClient(Document):
	def after_insert(self):
		# Crea automaticamente Customer ERPNext linkato (best-effort, async-safe)
		try:
			from thanatos_intel.integrations.erpnext_billing import get_or_create_customer
			get_or_create_customer(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"InvestigationClient.after_insert customer {self.name}")
