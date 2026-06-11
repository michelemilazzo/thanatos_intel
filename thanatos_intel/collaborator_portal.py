import frappe
from frappe.utils import now_datetime


def _collaborator(user):
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Affiliate Application", {"email": user},
		["name", "applicant_name", "collaborator_category"], as_dict=True)


def _ref_code(aff, user):
	if aff and aff.applicant_name:
		return frappe.scrub(aff.applicant_name)[:24].replace("_", "-")
	return (user or "").split("@")[0]


@frappe.whitelist()
def submit_lead(client_name, email=None, phone=None, country=None, service=None, notes=None):
	user = frappe.session.user
	aff = _collaborator(user)
	if not aff:
		frappe.throw("Non risulti registrato come collaboratore.")
	code = _ref_code(aff, user)
	if not email:
		email = "lead-%s@thanatos.local" % frappe.generate_hash(length=8)
	doc = frappe.get_doc({
		"doctype": "Investigation Client",
		"client_name": client_name,
		"email": email,
		"phone": phone,
		"country": country,
		"attribution_source": "Partner Portal",
		"referral_code": code,
		"acquired_at": now_datetime(),
	})
	sp = frappe.db.get_value("Sales Partner", {"partner_name": aff.applicant_name}, "name")
	if sp:
		doc.sales_partner = sp
	doc.insert(ignore_permissions=True)
	note = service and ("Servizio di interesse: %s. " % service) or ""
	note += notes or ""
	if note:
		frappe.get_doc({"doctype": "Comment", "comment_type": "Comment",
			"reference_doctype": "Investigation Client", "reference_name": doc.name,
			"content": "[Lead da collaboratore %s] %s" % (aff.applicant_name, note)}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "client": doc.name, "attributed_to": aff.applicant_name, "ref": code}
