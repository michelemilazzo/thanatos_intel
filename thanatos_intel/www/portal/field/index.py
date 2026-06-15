import frappe


def get_context(context):
	context.no_cache = 1
	context.body_class = "field-capture"
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/portal/field"
		raise frappe.Redirect

	context.title = "Cattura sul campo"
	context.activity_types = [
		"Incontro", "Pedinamento", "Sopralluogo", "Spostamento",
		"Chiamata", "Messaggio", "Email", "Osservazione", "Raccolta prove",
	]
	context.legal_bases = [
		"Parte della conversazione",
		"Consenso del soggetto",
		"Mandato del cliente",
		"Contratto detective (Legea 329/2003)",
		"Altro",
	]
	from thanatos_intel.thanatos_core.field_ops import my_cases
	context.cases = my_cases()
	return context
