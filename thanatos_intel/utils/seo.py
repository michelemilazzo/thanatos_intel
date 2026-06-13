import frappe


def gsc_code():
	"""Codice di verifica Google Search Console (da site_config). Metodo jinja
	(global) usabile anche dentro i macro importati senza `with context`."""
	return frappe.conf.get("google_site_verification") or ""
