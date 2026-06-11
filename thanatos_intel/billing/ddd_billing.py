"""Automazione billing per Agency Mandate (DDD):
al salvataggio del mandato genera/collega Customer + Quotation + CRM Deal.
Fail-safe: un errore di billing NON blocca mai il salvataggio del mandato.
Idempotente: usa i campi quotation_ref / crm_deal_ref sul mandato.
"""
import frappe

ITEM = "Due Diligence Diplomatica"
EUR_ACC = "Clienti EUR"


def _company():
	return frappe.defaults.get_global_default("company") or (
		frappe.get_all("Company", limit=1, pluck="name") or [None]
	)[0]


def _ensure_eur_receivable(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	acc = f"{EUR_ACC} - {abbr}"
	if not frappe.db.exists("Account", acc):
		rec = frappe.get_cached_value("Company", company, "default_receivable_account")
		parent = frappe.db.get_value("Account", rec, "parent_account") if rec else None
		a = frappe.new_doc("Account")
		a.account_name = EUR_ACC
		a.parent_account = parent
		a.company = company
		a.account_currency = "EUR"
		a.account_type = "Receivable"
		a.flags.ignore_mandatory = True
		a.insert(ignore_permissions=True)
	return acc


def _ensure_customer(name, company):
	if not frappe.db.exists("Customer", name):
		c = frappe.new_doc("Customer")
		c.customer_name = name
		c.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		c.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		c.customer_type = "Company"
		c.flags.ignore_mandatory = True
		c.insert(ignore_permissions=True)
	# conto crediti EUR se azienda in EUR
	if frappe.get_cached_value("Company", company, "default_currency") == "EUR":
		cdoc = frappe.get_doc("Customer", name)
		if not any(r.company == company for r in cdoc.accounts):
			cdoc.append("accounts", {"company": company, "account": _ensure_eur_receivable(company)})
			cdoc.flags.ignore_mandatory = True
			cdoc.save(ignore_permissions=True)
	return name


def _ensure_item(name=ITEM):
	if not frappe.db.exists("Item", name):
		it = frappe.new_doc("Item")
		it.item_code = it.item_name = name
		it.item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		it.stock_uom = "Nos"
		it.is_stock_item = 0
		it.is_sales_item = 1
		it.flags.ignore_mandatory = True
		it.insert(ignore_permissions=True)
	return name


def _quotation_items(doc, intest, fee):
	"""Righe quotation per singolo caso: dai Mandate Service Step se presenti,
	altrimenti una riga unica. I mandati investigativi non sono DD diplomatiche."""
	case_ref = doc.get("investigation_case") or doc.get("ddd_case") or doc.name
	if doc.get("investigation_case"):
		item = _ensure_item("Servizio Investigativo")
		label = "Servizio investigativo"
	else:
		item = _ensure_item()
		label = "Due Diligence diplomatica"
	steps = frappe.get_all("Mandate Service Step", filters={"mandate": doc.name},
		fields=["step_no", "title", "description", "fee"], order_by="step_no")
	if steps:
		return [{"item_code": item, "qty": 1, "rate": s.fee or 0,
			"description": f"{s.title} — {s.description or ''} ({case_ref})"} for s in steps]
	return [{"item_code": item, "qty": 1, "rate": fee,
		"description": f"{label} — {intest} ({case_ref})"}]


def on_mandate_update(doc, method=None):
	try:
		_run(doc)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"ddd_billing mandato {doc.name}")


def _run(doc):
	company = _company()
	if not company:
		return
	intest = (doc.get("intestatario_fattura") or "").strip()
	if not intest and doc.get("applicant"):
		intest = frappe.db.get_value("Applicant Profile", doc.applicant, "full_legal_name")
	if not intest:
		return
	cust = _ensure_customer(intest, company)
	fee = doc.get("fee_total") or 0

	# Quotation (idempotente via quotation_ref sul mandato)
	if not doc.get("quotation_ref") or not frappe.db.exists("Quotation", doc.get("quotation_ref")):
		q = frappe.new_doc("Quotation")
		q.quotation_to = "Customer"
		q.party_name = cust
		q.company = company
		# Numerazione dedicata dell'agenzia che fattura le DD passaporti (es. ARES-QTN-AAAA-)
		if doc.get("ddd_case") and doc.get("billing_entity"):
			series = "ARES-QTN-.YYYY.-"
			opts = (frappe.get_meta("Quotation").get_field("naming_series").options or "")
			if series in opts.split("\n"):
				q.naming_series = series
		q.currency = doc.get("currency") or "EUR"
		for row in _quotation_items(doc, intest, fee):
			q.append("items", row)
		q.flags.ignore_mandatory = True
		q.insert(ignore_permissions=True)
		doc.db_set("quotation_ref", q.name, update_modified=False)

	# CRM Deal (idempotente via crm_deal_ref)
	if frappe.db.exists("DocType", "CRM Deal") and (
		not doc.get("crm_deal_ref") or not frappe.db.exists("CRM Deal", doc.get("crm_deal_ref"))
	):
		if frappe.db.exists("DocType", "CRM Organization") and not frappe.db.exists("CRM Organization", intest):
			o = frappe.new_doc("CRM Organization")
			o.organization_name = intest
			o.flags.ignore_mandatory = True
			o.insert(ignore_permissions=True)
		d = frappe.new_doc("CRM Deal")
		open_st = frappe.db.get_value("CRM Deal Status", {"name": "Qualification"}, "name") or \
			frappe.get_all("CRM Deal Status", limit=1, pluck="name")[0]
		d.status = open_st
		for fn, val in [("organization", intest), ("currency", doc.get("currency") or "EUR"),
			("deal_value", fee), ("annual_revenue", fee)]:
			if d.meta.get_field(fn):
				d.set(fn, val)
		d.flags.ignore_mandatory = True
		d.insert(ignore_permissions=True)
		doc.db_set("crm_deal_ref", d.name, update_modified=False)
