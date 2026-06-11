import frappe
from frappe.model.document import Document


class AIUsageLog(Document):
	def before_save(self):
		# costo cliente = costo reale x markup
		if self.real_cost and not self.client_cost:
			try:
				markup = float(frappe.conf.get("infra_markup") or 3.0)
			except Exception:
				markup = 3.0
			self.client_cost = round(float(self.real_cost) * markup, 2)


@frappe.whitelist()
def log_usage(client, provider, real_cost, model=None, tokens_in=0, tokens_out=0, reference=None, usage_date=None):
	"""Registra un consumo AI (chiamato dal gateway/job di metering)."""
	from frappe.utils import nowdate
	doc = frappe.get_doc({
		"doctype": "AI Usage Log", "client": client, "provider": provider,
		"model": model, "tokens_in": tokens_in or 0, "tokens_out": tokens_out or 0,
		"real_cost": real_cost, "reference": reference, "usage_date": usage_date or nowdate(),
	})
	doc.insert(ignore_permissions=True)
	return doc.name
