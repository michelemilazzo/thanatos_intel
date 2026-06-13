import frappe

no_cache = 1
sitemap = 0

TARGET_TYPES = ["Email", "IP", "Domain", "Url", "Hash", "Company", "Person",
                "Phone", "Username", "Wallet", "Vessel", "Aircraft"]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/osint/sorgenti"
		raise frappe.Redirect
	context.no_cache = 1
	context.target_types = TARGET_TYPES
	context.is_admin = "System Manager" in frappe.get_roles()
	from thanatos_intel.osint import source_registry
	context.overview = source_registry.overview()
