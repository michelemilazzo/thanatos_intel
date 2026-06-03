"""Bridge tra Frappe CRM (crm app) e Thanatos Intel.

Convertono CRM Lead → Investigation Client e CRM Deal → Investigative Case.
Stage del CRM Deal mappato a status Investigation Case.
"""
import frappe
from frappe.utils import now_datetime


# Mappa CRM Deal stage → Investigation Case status (best-effort)
STAGE_MAP = {
	"Qualification": "Draft",
	"Demo/Making": "Open",
	"Proposal": "Open",
	"Negotiation": "In Progress",
	"Ready to Close": "Review",
	"Won": "Closed",
	"Lost": "Cancelled",
}


@frappe.whitelist()
def convert_lead_to_client(lead_name: str) -> dict:
	"""Crea un Investigation Client partendo da CRM Lead."""
	lead = frappe.get_doc("CRM Lead", lead_name)

	# Email è il primary key del client
	email = (lead.email or "").strip().lower()
	if not email:
		frappe.throw("CRM Lead senza email — impossibile creare Investigation Client")

	if frappe.db.exists("Investigation Client", email):
		return {"ok": True, "client": email, "created": False}

	# Mappa lead.no_of_employees / industry → client_type
	if (lead.organization or lead.company_name) and (lead.no_of_employees or "").strip():
		client_type = "Company"
	elif lead.organization or lead.company_name:
		client_type = "Company"
	else:
		client_type = "Individual"

	client_name = (
		f"{lead.first_name or ''} {lead.last_name or ''}".strip()
		or lead.organization
		or lead.company_name
		or email
	)

	client = frappe.get_doc({
		"doctype": "Investigation Client",
		"client_name": client_name,
		"client_type": client_type,
		"email": email,
		"phone": lead.mobile_no or lead.phone or "",
		"vat_number": lead.get("tax_id") or "",
		"address": (lead.get("address") or "")[:400] if lead.get("address") else "",
	}).insert(ignore_permissions=True)

	# Linka il lead ↔ client
	frappe.db.set_value("CRM Lead", lead_name, "converted", 1)
	frappe.db.commit()
	return {"ok": True, "client": client.name, "created": True}


@frappe.whitelist()
def convert_deal_to_case(deal_name: str, case_type: str = "Fraud") -> dict:
	"""Crea un Investigative Case partendo da CRM Deal."""
	deal = frappe.get_doc("CRM Deal", deal_name)

	# Risolvi cliente: prova prima l'email del Deal
	client_email = (deal.email or "").strip().lower()
	if not client_email:
		# Fallback: cerca il Lead originario
		if deal.get("lead"):
			lead_email = frappe.db.get_value("CRM Lead", deal.lead, "email")
			client_email = (lead_email or "").strip().lower()

	client = None
	if client_email and frappe.db.exists("Investigation Client", client_email):
		client = client_email

	# Crea il caso
	case = frappe.get_doc({
		"doctype": "Investigation Case",
		"case_title": deal.deal_name or deal.name,
		"case_type": case_type if case_type in ("Fraud", "Corporate", "Cyber", "Seizure", "Family", "Asset Recovery") else "Fraud",
		"client": client,
		"status": STAGE_MAP.get(deal.status, "Draft"),
		"priority": "High" if deal.get("probability", 0) >= 70 else "Normal",
		"description": f"Convertito da CRM Deal {deal.name}\n\n{deal.description or ''}",
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "case": case.name, "case_number": case.case_number}


def sync_deal_stage(doc, method=None):
	"""Hook: quando lo stage di un CRM Deal cambia, aggiorna il Case linkato."""
	# Cerca un Investigation Case col deal_name nel description (semplice mapping)
	cases = frappe.get_all(
		"Investigation Case",
		filters={"description": ["like", f"%CRM Deal {doc.name}%"]},
		pluck="name",
	)
	new_status = STAGE_MAP.get(doc.status)
	if not new_status:
		return
	for c in cases:
		try:
			frappe.db.set_value("Investigation Case", c, "status", new_status, update_modified=False)
		except Exception:
			pass
