import frappe
from frappe.model.document import Document


class CollaboratorCategory(Document):
	pass


def allowed_service_codes(category):
	"""Codici servizio che una Collaborator Category puo proporre."""
	if not category:
		return []
	cat = frappe.get_doc("Collaborator Category", category)
	if cat.all_services:
		return frappe.get_all("Service Catalog", filters={"is_active": 1}, pluck="name")
	cats = [r.service_category for r in cat.allowed_service_categories]
	if not cats:
		return []
	return frappe.get_all("Service Catalog", filters={"is_active": 1, "category": ["in", cats]}, pluck="name")
