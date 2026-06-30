import frappe
from thanatos_intel.thanatos_billing.doctype.collaborator_category.collaborator_category import featured_categories
from thanatos_intel.thanatos_billing.doctype.commission_rule.commission_rule import resolve_commission, commission_for_label


def get_context(context):
	context.no_cache = 1
	user = frappe.session.user
	aff = None
	if user and user != "Guest":
		aff = frappe.db.get_value(
			"Affiliate Application", {"email": user},
			["name", "applicant_name", "collaborator_category", "status"], as_dict=True)
	context.collaborator = aff
	cat = aff.collaborator_category if aff else None
	context.category = cat
	feat = set(featured_categories(cat)) if cat else set()
	context.featured = feat
	code = frappe.scrub(aff.applicant_name)[:24].replace("_", "-") if (aff and aff.applicant_name) else ""
	context.referral_code = code
	context.referral_link = ("https://thanatos.agency/?ref=" + code) if code else ""

	# i miei clienti attribuiti + commissione stimata
	clients, est, attributed = [], 0.0, 0.0
	if code:
		clients = frappe.get_all("Investigation Client", filters={"referral_code": code},
			fields=["client_name", "subscription_plan", "subscription_status", "total_spent", "acquired_at"],
			order_by="acquired_at desc")
		partner_label = (aff and aff.get("collaborator_category")) or "partner"
		for c in clients:
			spent = float(c.total_spent or 0)
			attributed += spent
			rule = resolve_commission(plan=c.subscription_plan, partner_level=partner_label) if c.subscription_plan else None
			if rule and spent:
				est += commission_for_label(rule, spent, partner_label)
	context.my_clients = clients
	context.my_clients_count = len(clients)
	context.attributed_total = round(attributed, 2)
	context.est_commission = round(est, 2)

	# fatture/pagamenti dei clienti referral (Usage Events + Stripe Subscription)
	invoices = []
	payouts = []
	if code and clients:
		client_names = [c.name for c in clients if c.get("name")]
		if not client_names:
			client_names = frappe.get_all("Investigation Client",
			                              filters={"referral_code": code}, pluck="name")
		if client_names:
			# Usage Events pagati
			ues = frappe.get_all("Usage Event",
			    filters={"client": ["in", client_names], "status": ["in", ["Paid", "Invoiced"]]},
			    fields=["client", "service", "total", "currency", "paid_at", "creation"],
			    order_by="creation desc", limit=30)
			for ue in ues:
				client_display = frappe.db.get_value("Investigation Client", ue.client, "client_name") or ue.client
				invoices.append({
				    "client": client_display,
				    "description": ue.service or "Servizio",
				    "amount": float(ue.total or 0),
				    "currency": ue.currency or "EUR",
				    "date": ue.paid_at or ue.creation,
				    "type": "pay-per-use",
				})
			# Abbonamenti da Stripe Subscription
			subs = frappe.get_all("Stripe Subscription",
			    filters={"investigation_client": ["in", client_names],
			             "status": ["in", ["active", "trialing"]]},
			    fields=["investigation_client", "subscription_plan", "amount",
			            "currency", "current_period_end", "status"])
			for s in subs:
				client_display = frappe.db.get_value("Investigation Client",
				    s.investigation_client, "client_name") or s.investigation_client
				invoices.append({
				    "client": client_display,
				    "description": f"Abbonamento {s.subscription_plan or ''}",
				    "amount": float(s.amount or 0),
				    "currency": (s.currency or "EUR").upper(),
				    "date": s.current_period_end,
				    "type": "subscription",
				})
			# Party Payouts (commissioni già liquidate)
			if aff:
				payouts = frappe.get_all("Party Payout",
				    filters={"party_name": aff.applicant_name,
				             "status": ["in", ["Approved", "Paid"]]},
				    fields=["name", "amount", "currency", "status", "creation"],
				    order_by="creation desc", limit=10)
	context.billing_invoices = sorted(invoices, key=lambda x: str(x.get("date") or ""), reverse=True)[:20]
	context.payouts = payouts
	context.total_billed = round(sum(i["amount"] for i in invoices), 2)
	context.erp_url = frappe.conf.get("erpnext_endpoint") or "https://erp.onekeyco.com"

	# catalogo
	svcs = frappe.get_all("Service Catalog", filters={"is_active": 1},
		fields=["name", "service_name", "category", "price", "currency"], order_by="category, price")
	groups = {}
	for s in svcs:
		groups.setdefault(s.category, []).append(s)
	ordered = sorted(groups.items(), key=lambda kv: (kv[0] not in feat, kv[0]))
	context.groups = [{"category": c, "featured": c in feat, "services": items} for c, items in ordered]
	context.total_services = len(svcs)
	return context
