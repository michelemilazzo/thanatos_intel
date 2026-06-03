"""Controller per /upload-test — inietta csrf_token nel contesto."""
import frappe


def get_context(context):
	context.no_cache = 1
	try:
		context.csrf_token = frappe.sessions.get_csrf_token()
	except Exception:
		context.csrf_token = ""
	return context


sitemap = False
