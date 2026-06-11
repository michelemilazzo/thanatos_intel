import frappe
from frappe.model.document import Document


class CommissionRule(Document):
	def validate(self):
		if self.applies_to == "Plan" and not self.subscription_plan:
			frappe.throw("Subscription Plan richiesto quando Applies To = Plan")
		if self.applies_to == "Service" and not self.service:
			frappe.throw("Service richiesto quando Applies To = Service")


def resolve_commission(plan=None, service=None, partner_level=None):
	"""Restituisce la Commission Rule attiva piu specifica per una vendita.
	Specificita: match Plan/Service > Any; partner_level valorizzato > vuoto; poi priority."""
	rules = frappe.get_all(
		"Commission Rule",
		filters={"active": 1},
		fields=["name", "applies_to", "subscription_plan", "service",
			"partner_level", "commission_type", "commission_rate",
			"max_recurring_months", "priority"],
	)
	def ok(r):
		if r.applies_to == "Plan" and r.subscription_plan != plan:
			return False
		if r.applies_to == "Service" and r.service != service:
			return False
		if r.partner_level and r.partner_level != partner_level:
			return False
		return True
	cands = [r for r in rules if ok(r)]
	if not cands:
		return None
	def score(r):
		return (2 if r.applies_to in ("Plan", "Service") else 0,
			1 if r.partner_level else 0, r.priority or 0)
	return max(cands, key=score)
