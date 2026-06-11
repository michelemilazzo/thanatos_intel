import frappe
from frappe.model.document import Document


class CollaboratorCategory(Document):
	pass


def featured_service_codes(category):
	"""Servizi in EVIDENZA per la categoria collaboratore.
	NB il collaboratore puo vendere TUTTI i servizi: questi sono solo quelli
	messi in risalto (la sua specializzazione). all_services -> nessuna evidenza
	specifica (vende tutto uniformemente)."""
	if not category:
		return []
	cat = frappe.get_doc("Collaborator Category", category)
	if cat.all_services:
		return []
	cats = [r.service_category for r in cat.allowed_service_categories]
	if not cats:
		return []
	return frappe.get_all("Service Catalog", filters={"is_active": 1, "category": ["in", cats]}, pluck="name")


def featured_categories(category):
	"""Nomi delle categorie di servizio in evidenza per la categoria collaboratore."""
	if not category:
		return []
	cat = frappe.get_doc("Collaborator Category", category)
	return [r.service_category for r in cat.allowed_service_categories]
