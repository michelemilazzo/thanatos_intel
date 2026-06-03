"""Ganci di integrazione ERPNext (Customer, Item, Sales Invoice, Payment Entry).

- Investigation Client → Customer (1:1)
- Service Catalog → Item (1:1, on demand al primo Usage Event)
- Usage Event (Paid) → Sales Invoice + Payment Entry
"""
import frappe
from frappe.utils import flt, now_datetime, today

# Configurazione Thanatos default per ERPNext
DEFAULT_ITEM_GROUP = "Services"


def _company_currency() -> str:
	"""Risolve la currency della company corrente in modo robusto (no cache stale)."""
	c = frappe.db.get_default("company") or frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
	if not c:
		return "EUR"
	return frappe.db.get_value("Company", c, "default_currency") or "EUR"


# Compatibilità con codice legacy
DEFAULT_CURRENCY = "EUR"
DEFAULT_COMPANY = None


# ====== CUSTOMER ======

def get_or_create_customer(client_name: str) -> str | None:
	"""Crea il Customer ERPNext per un Investigation Client se non esiste."""
	if not client_name:
		return None
	client = frappe.get_doc("Investigation Client", client_name)

	# Se già linkato, ritorna
	if client.erp_customer_id and frappe.db.exists("Customer", client.erp_customer_id):
		return client.erp_customer_id

	# Cerca per email o nome
	existing = frappe.db.get_value("Customer", {"customer_name": client.client_name}, "name")
	if existing:
		frappe.db.set_value("Investigation Client", client_name, "erp_customer_id", existing)
		return existing

	# Mappa client_type → customer_type
	ct_map = {
		"Individual": "Individual",
		"Company": "Company",
		"Law Firm": "Company",
		"Accounting Firm": "Company",
		"Other": "Individual",
	}
	# Mappa preferred_language → codice Frappe (en/it/ro). Customer.language è un Link a Language.
	lang_map = {"Italian": "it", "Romanian": "ro", "English": "en"}
	lang_code = lang_map.get(client.preferred_language, "en")
	if not frappe.db.exists("Language", lang_code):
		lang_code = None  # lascia il default Frappe

	# Customer Group: pref leaf "Commercial" (esiste in ERPNext default)
	cg = _pick_leaf("Customer Group", ["Commercial", "Individual", "All Customer Groups"])
	terr = _pick_leaf("Territory", ["Romania", "Italy", "Rest Of The World", "All Territories"])

	# Allinea customer.default_currency a company currency per evitare InvalidCurrency
	cust_currency = _company_currency()

	cust = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": client.client_name,
		"customer_type": ct_map.get(client.client_type, "Individual"),
		"customer_group": cg,
		"territory": terr,
		"tax_id": client.vat_number or None,
		"default_currency": cust_currency,
		"language": lang_code,
	})
	cust.insert(ignore_permissions=True)

	# Linka il Customer all'account Receivable EUR per la company (evita InvalidCurrency)
	try:
		company = get_default_company()
		eur_acc = _ensure_eur_receivable_account(company) if company else None
		if company and eur_acc:
			already = frappe.db.exists(
				"Party Account",
				{"parent": cust.name, "parenttype": "Customer", "company": company},
			)
			if not already:
				row = frappe.get_doc({
					"doctype": "Party Account",
					"parent": cust.name,
					"parenttype": "Customer",
					"parentfield": "accounts",
					"company": company,
					"account": eur_acc,
				})
				row.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"link customer to EUR account {cust.name}")

	frappe.db.set_value("Investigation Client", client_name, "erp_customer_id", cust.name)
	return cust.name


def _pick_leaf(doctype: str, candidates: list[str]) -> str | None:
	"""Restituisce il primo candidato che esiste come leaf (is_group=0)."""
	for c in candidates:
		row = frappe.db.get_value(doctype, c, ["name", "is_group"], as_dict=True)
		if row and not row.is_group:
			return row.name
	# Fallback: qualsiasi leaf esistente
	row = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	return row


# ====== ITEM ======

def get_or_create_item(service_code: str) -> str | None:
	"""Crea un Item ERPNext per un Service Catalog se non esiste."""
	if not service_code:
		return None
	svc = frappe.get_doc("Service Catalog", service_code)

	if svc.erp_item_code and frappe.db.exists("Item", svc.erp_item_code):
		return svc.erp_item_code

	# Cerca per code o name
	existing = frappe.db.get_value("Item", svc.service_code, "name")
	if existing:
		frappe.db.set_value("Service Catalog", service_code, "erp_item_code", existing)
		return existing

	# Assicura Item Group "Services"
	_ensure_item_group()
	item = frappe.get_doc({
		"doctype": "Item",
		"item_code": svc.service_code,
		"item_name": svc.service_name[:140],
		"description": svc.description or svc.service_name,
		"item_group": DEFAULT_ITEM_GROUP,
		"stock_uom": "Nos",
		"is_stock_item": 0,  # servizio: NON è un magazzino
		"include_item_in_manufacturing": 0,
		"is_sales_item": 1,
		"is_purchase_item": 0,
		"standard_rate": flt(svc.price or 0),
	})
	item.insert(ignore_permissions=True)
	frappe.db.set_value("Service Catalog", service_code, "erp_item_code", item.name)
	return item.name


def _ensure_item_group():
	if not frappe.db.exists("Item Group", DEFAULT_ITEM_GROUP):
		try:
			ig = frappe.get_doc({
				"doctype": "Item Group",
				"item_group_name": DEFAULT_ITEM_GROUP,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			})
			ig.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ensure_item_group")


# ====== SALES INVOICE ======

def get_default_company() -> str | None:
	global DEFAULT_COMPANY
	if DEFAULT_COMPANY:
		return DEFAULT_COMPANY
	c = frappe.db.get_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")
	if not c:
		# pick the first existing company
		c = frappe.db.get_value("Company", {}, "name")
	DEFAULT_COMPANY = c
	return c


def _ensure_eur_receivable_account(company: str) -> str | None:
	"""Crea un account Receivable in EUR per la company, se non esiste."""
	# Cerca account Receivable in EUR esistente
	existing = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Receivable", "account_currency": "EUR", "is_group": 0},
		"name",
	)
	if existing:
		return existing

	# Crea l'account sotto il primo group Receivable (es. "Creante")
	parent = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Receivable", "is_group": 1},
		"name",
	) or frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Asset", "is_group": 1},
		"name",
	)
	if not parent:
		return None

	try:
		acc = frappe.get_doc({
			"doctype": "Account",
			"account_name": "Debitori EUR (Thanatos)",
			"parent_account": parent,
			"company": company,
			"account_type": "Receivable",
			"account_currency": "EUR",
			"is_group": 0,
		})
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ensure_eur_receivable_account")
		return None


def create_sales_invoice_for_usage_event(usage_event_name: str, submit: bool = False) -> str | None:
	"""Genera una Sales Invoice ERPNext per un Usage Event (status Paid)."""
	ue = frappe.get_doc("Usage Event", usage_event_name)
	if ue.erp_invoice_id and frappe.db.exists("Sales Invoice", ue.erp_invoice_id):
		return ue.erp_invoice_id

	customer = get_or_create_customer(ue.client)
	if not customer:
		frappe.throw(f"Cliente non risolvibile per Usage Event {usage_event_name}")
	item_code = get_or_create_item(ue.service)
	if not item_code:
		frappe.throw(f"Service Catalog non risolvibile per Usage Event {usage_event_name}")

	company = get_default_company()
	if not company:
		frappe.throw("Nessuna Company ERPNext configurata")

	company_currency = _company_currency()
	# Per MVP usa EUR (currency company): assicura un account Receivable in EUR esista
	debit_to = _ensure_eur_receivable_account(company) if company_currency == "EUR" else None

	si_data = {
		"doctype": "Sales Invoice",
		"customer": customer,
		"company": company,
		"posting_date": today(),
		"due_date": today(),
		"currency": company_currency,
		"conversion_rate": 1.0,
		"remarks": f"Auto da Usage Event {ue.name} | importo originale: {ue.currency} {ue.total}",
		"items": [{
			"item_code": item_code,
			"item_name": frappe.db.get_value("Service Catalog", ue.service, "service_name"),
			"qty": flt(ue.quantity or 1),
			"rate": flt(ue.unit_price or 0),
			"description": f"Service: {ue.service} | Case: {ue.case or '-'}",
		}],
	}
	if debit_to:
		si_data["debit_to"] = debit_to
	inv = frappe.get_doc(si_data)
	inv.insert(ignore_permissions=True)
	if submit:
		try:
			inv.submit()
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"submit SI {inv.name}")

	frappe.db.set_value("Usage Event", usage_event_name, "erp_invoice_id", inv.name)
	frappe.db.commit()
	return inv.name


# ====== Hook: chiamato da Usage Event.on_payment_confirmed ======

def after_payment(usage_event_name: str):
	"""Hook unico chiamato quando un Usage Event passa a Paid (webhook Stripe).

	Crea il Sales Invoice in stato DRAFT (no submit). Il contabile lo sottometterà
	manualmente dal desk dopo aver verificato che i conti EUR siano disponibili
	(o configurato un Account Receivable EUR via Chart of Accounts).
	"""
	try:
		si_name = create_sales_invoice_for_usage_event(usage_event_name, submit=False)
		return {"ok": True, "sales_invoice": si_name, "submit_pending": True}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"after_payment {usage_event_name}")
		return {"ok": False, "error": str(e)[:300]}
