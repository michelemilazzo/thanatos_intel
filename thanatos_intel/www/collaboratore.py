import frappe
from thanatos_intel.thanatos_billing.doctype.collaborator_category.collaborator_category import featured_categories
from thanatos_intel.thanatos_billing.doctype.commission_rule.commission_rule import resolve_commission


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
	context.referral_link = ("https://thanatos.onekeyco.com/?ref=" + code) if code else ""

	# i miei clienti attribuiti + commissione stimata
	clients, est, attributed = [], 0.0, 0.0
	if code:
		clients = frappe.get_all("Investigation Client", filters={"referral_code": code},
			fields=["client_name", "subscription_plan", "subscription_status", "total_spent", "acquired_at"],
			order_by="acquired_at desc")
		for c in clients:
			spent = float(c.total_spent or 0)
			attributed += spent
			rule = resolve_commission(plan=c.subscription_plan) if c.subscription_plan else None
			if rule and spent:
				est += spent * (float(rule.commission_rate or 0) / 100)
	context.my_clients = clients
	context.my_clients_count = len(clients)
	context.attributed_total = round(attributed, 2)
	context.est_commission = round(est, 2)

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
