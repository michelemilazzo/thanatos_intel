import frappe

no_cache = 1


def get_context(context):
	"""Esegue il logout e reindirizza alla home."""
	try:
		if getattr(frappe.session, "user", "Guest") != "Guest":
			frappe.local.login_manager.logout()
			frappe.db.commit()
	except Exception:
		frappe.clear_cache(user=frappe.session.user)
	frappe.local.flags.redirect_location = "/"
	raise frappe.Redirect
