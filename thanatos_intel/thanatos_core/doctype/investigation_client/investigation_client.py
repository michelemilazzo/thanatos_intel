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
		# Operazione di SISTEMA: gira con ignore_permissions (il cliente non ha
		# accesso ai doctype Address/Customer/Contact) e NON deve far trapelare
		# messaggi/errori al cliente. Best-effort: non blocca mai il salvataggio.
		prev_perm = frappe.flags.ignore_permissions
		msg_len = len(frappe.local.message_log or [])
		frappe.flags.ignore_permissions = True
		try:
			from thanatos_intel.integrations.erpnext_billing import sync_client
			sync_client(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"InvestigationClient.on_update sync {self.name}")
		finally:
			frappe.flags.ignore_permissions = prev_perm
			if frappe.local.message_log and len(frappe.local.message_log) > msg_len:
				frappe.local.message_log = frappe.local.message_log[:msg_len]
