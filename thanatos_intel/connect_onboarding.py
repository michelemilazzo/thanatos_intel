"""Onboarding Stripe Connect Express per collaboratori: crea connected account +
account link, salva stripe_connect_account_id sull Affiliate Application. I transfer
del profit-split (revenue_engine.execute_payout) usano poi quell id."""
import frappe
from thanatos_intel.integrations.stripe_bridge import _get_stripe

RETURN_URL = "https://thanatos.agency/collaboratore?connect=done"
REFRESH_URL = "https://thanatos.agency/collaboratore?connect=refresh"


def _affiliate(user):
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Affiliate Application", {"email": user},
		["name", "applicant_name", "stripe_connect_account_id"], as_dict=True)


@frappe.whitelist()
def start_onboarding():
	aff = _affiliate(frappe.session.user)
	if not aff:
		frappe.throw("Non risulti registrato come collaboratore.")
	s = _get_stripe()
	acct_id = aff.stripe_connect_account_id
	if not acct_id:
		acct = s.Account.create(type="express", country="IT", email=frappe.session.user,
			capabilities={"transfers": {"requested": True}},
			metadata={"affiliate": aff.name, "name": aff.applicant_name or ""})
		acct_id = acct.id
		frappe.db.set_value("Affiliate Application", aff.name, "stripe_connect_account_id", acct_id)
		frappe.db.commit()
	link = s.AccountLink.create(account=acct_id, refresh_url=REFRESH_URL,
		return_url=RETURN_URL, type="account_onboarding")
	return {"url": link.url, "account": acct_id}


@frappe.whitelist()
def status():
	aff = _affiliate(frappe.session.user)
	if not aff or not aff.stripe_connect_account_id:
		return {"connected": False}
	s = _get_stripe()
	acct = s.Account.retrieve(aff.stripe_connect_account_id)
	return {"connected": True, "account": aff.stripe_connect_account_id,
		"payouts_enabled": acct.get("payouts_enabled"),
		"details_submitted": acct.get("details_submitted")}


def connect_account_for(assignee_type, assignee_email):
	"""id del connected account di un collaboratore (per popolare case_assignments)."""
	return frappe.db.get_value("Affiliate Application",
		{"email": assignee_email}, "stripe_connect_account_id")


def sync_assignment_connect_accounts(doc, method=None):
	"""Hook Investigation Case validate: popola stripe_connect_account_id su ogni
	case_assignment dal connected account del collaboratore (Affiliate Application)."""
	for a in (doc.get("case_assignments") or []):
		if not a.get("stripe_connect_account_id") and a.get("assignee_email"):
			acct = frappe.db.get_value("Affiliate Application",
				{"email": a.assignee_email}, "stripe_connect_account_id")
			if acct:
				a.stripe_connect_account_id = acct
