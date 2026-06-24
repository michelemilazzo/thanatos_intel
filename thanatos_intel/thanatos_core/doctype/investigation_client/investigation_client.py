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

	def on_update(self):
		# Allinea i dati alle entità native ERPNext (Customer/Address/Contact).
		# Best-effort: un errore di sync non deve mai bloccare il salvataggio.
		try:
			from thanatos_intel.integrations.erpnext_billing import sync_client
			sync_client(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"InvestigationClient.on_update sync {self.name}")
