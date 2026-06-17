# Copyright (c) 2026, MMOS and contributors
"""Self-service two-factor (Google Authenticator) opt-in for any logged-in user.

2FA at login is global-enabled but enforced only for users holding the opt-in
role ``Two-Factor Login`` (the only role flagged ``two_factor_auth``). Any user
— staff or client — can switch it on/off for their own account here; nobody is
forced. On the next login Frappe shows the QR to enrol Google Authenticator.
"""

import frappe
from frappe.utils import cint

OPTIN_ROLE = "Two-Factor Login"


@frappe.whitelist()
def get_status():
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Login required.")
	return {"enabled": OPTIN_ROLE in frappe.get_roles(user)}


@frappe.whitelist()
def set_two_factor(enable):
	"""Add/remove the 2FA opt-in role on the current user only."""
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw("Not available for this account.")
	enable = cint(enable)
	doc = frappe.get_doc("User", user)
	has = any(r.role == OPTIN_ROLE for r in doc.roles)
	if enable and not has:
		doc.append("roles", {"role": OPTIN_ROLE})
		doc.save(ignore_permissions=True)
	elif not enable and has:
		doc.roles = [r for r in doc.roles if r.role != OPTIN_ROLE]
		doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"enabled": bool(enable)}
