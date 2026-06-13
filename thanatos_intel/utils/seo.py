import frappe


def update_website_context(context):
	"""Inietta in ogni pagina web la verifica Search Console (da site_config)."""
	context["google_site_verification"] = frappe.conf.get("google_site_verification") or ""
