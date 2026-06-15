"""API per la cattura sul campo (pagina /portal/field).

Crea Field Activity reali dai dati raccolti dall'investigatore in mobilità:
GPS, registrazione audio, foto, nota. Gli allegati diventano reperti in
catena di custodia (SHA-256) al submit dell'attività.
"""
import frappe
from frappe import _


def _current_investigator():
	"""Investigator collegato all'utente loggato, se esiste."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Login richiesto"), frappe.PermissionError)
	return frappe.db.get_value("Investigator", {"platform_user": user}, "name")


@frappe.whitelist()
def my_cases():
	"""Casi su cui l'investigatore loggato può registrare attività."""
	inv = _current_investigator()
	filters = {}
	if inv and "System Manager" not in frappe.get_roles():
		filters["assigned_investigator"] = inv
	return frappe.get_all(
		"Investigation Case",
		filters=filters,
		fields=["name", "case_title", "status"],
		order_by="modified desc",
		limit=50,
	)


@frappe.whitelist(methods=["POST"])
def log_activity(
	investigation_case,
	activity_type,
	activity_title=None,
	start_datetime=None,
	end_datetime=None,
	geo_lat=None,
	geo_lng=None,
	geo_accuracy=None,
	location_address=None,
	subjects=None,
	narrative=None,
	legal_basis=None,
	consent_confirmed=0,
	attachments=None,
	submit=0,
):
	"""Crea una Field Activity dai dati della pagina di cattura.

	attachments: lista JSON di {file_url, caption, captured_at}.
	"""
	inv = _current_investigator()
	if not frappe.db.exists("Investigation Case", investigation_case):
		frappe.throw(_("Caso non trovato"))

	doc = frappe.get_doc({
		"doctype": "Field Activity",
		"investigation_case": investigation_case,
		"activity_type": activity_type,
		"activity_title": activity_title,
		"investigator": inv,
		"start_datetime": start_datetime or frappe.utils.now_datetime(),
		"end_datetime": end_datetime,
		"geo_lat": flt_or_none(geo_lat),
		"geo_lng": flt_or_none(geo_lng),
		"geo_accuracy": flt_or_none(geo_accuracy),
		"location_address": location_address,
		"subjects": subjects,
		"narrative": narrative,
		"legal_basis": legal_basis,
		"consent_confirmed": 1 if str(consent_confirmed) in ("1", "true", "True") else 0,
	})

	for row in frappe.parse_json(attachments or "[]"):
		if row.get("file_url"):
			doc.append("attachments", {
				"file": row["file_url"],
				"caption": row.get("caption"),
				"captured_at": row.get("captured_at") or doc.start_datetime,
			})

	doc.insert(ignore_permissions=True)
	if str(submit) in ("1", "true", "True"):
		doc.submit()
	frappe.db.commit()
	return {"ok": True, "name": doc.name, "docstatus": doc.docstatus}


def flt_or_none(v):
	try:
		return float(v) if v not in (None, "", "null") else None
	except (TypeError, ValueError):
		return None
