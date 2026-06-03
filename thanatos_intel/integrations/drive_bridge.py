"""Bridge Frappe Drive: cartelle per case + Evidence come Drive Document.

Drive di Frappe usa una struttura Team Drive con Drive File documents.
Crea: Drive folder per ogni case + uploaded files come Drive File.
"""
import frappe


THANATOS_TEAM_NAME = "thanatos-investigations"  # Drive Team default; può essere creato a mano dal desk


def ensure_case_folder(case_name: str) -> str | None:
	"""Crea (o restituisce) il Drive File folder per un Investigative Case.

	Struttura: /Cases/CASE-YYYY-NNNN/
	"""
	if not frappe.db.has_table("Drive File"):
		return None
	case = frappe.get_doc("Investigation Case", case_name)

	# Cerca/crea team
	team = frappe.db.get_value("Drive Team", THANATOS_TEAM_NAME, "name")
	if not team:
		# Drive Team creazione richiede membri; lascia che lo crei l'utente.
		return None

	folder_name = case.case_number or case.name
	# Cerca un Drive File con title=case_number, is_group=1
	existing = frappe.db.get_value("Drive File", {
		"title": folder_name,
		"team": team,
		"is_group": 1,
	}, "name")
	if existing:
		return existing

	try:
		folder = frappe.get_doc({
			"doctype": "Drive File",
			"title": folder_name,
			"is_group": 1,
			"team": team,
			"color": "#C8A96E",  # oro Thanatos
		})
		folder.insert(ignore_permissions=True)
		return folder.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"ensure_case_folder {case_name}")
		return None


@frappe.whitelist()
def link_case_to_drive(case_name: str) -> dict:
	"""Esposto: crea il folder Drive per un case e ritorna il link."""
	folder = ensure_case_folder(case_name)
	if folder:
		return {"ok": True, "drive_folder": folder, "url": f"/drive/folder/{folder}"}
	return {"ok": False, "reason": "Drive Team non configurato o tabella mancante"}
