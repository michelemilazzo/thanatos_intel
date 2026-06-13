import frappe

no_cache = 1
sitemap = 0


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/osint/chiavi"
		raise frappe.Redirect
	if "System Manager" not in frappe.get_roles():
		raise frappe.PermissionError("Riservato a System Manager")
	context.no_cache = 1
	from thanatos_intel.osint import api_keys
	context.sources = api_keys.key_sources()
	context.configured = sum(1 for s in context.sources if s["configured"])
	context.total = len(context.sources)
