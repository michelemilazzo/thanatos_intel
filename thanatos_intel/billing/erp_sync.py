"""
Sync Infrastructure Cost items + emit monthly Sales Invoice on the MMOS bookkeeping site
(erp.onekeyco.com). Auth via API key/secret (`erpnext_endpoint`, `erpnext_api_key`,
`erpnext_api_secret` in site_config of thanatos.onekeyco.com).

The flow:
  thanatos.onekeyco.com    →    erp.onekeyco.com
  (Infrastructure Cost)         (Item + monthly Sales Invoice)

  Customer (seller) = MMOS / OneKeyCo (default company on ERP)
  Customer (buyer)  = "Thanatos Investigazioni S.R.L."
"""
import json
import frappe
from frappe import _
from frappe.utils import (now_datetime, get_first_day, get_last_day,
                          add_months, flt)


# ---------- low-level HTTP client ----------

def _erp_endpoint() -> str | None:
	return (frappe.conf.get("erpnext_endpoint")
	        or "https://erp.onekeyco.com").rstrip("/")


def _erp_headers() -> dict | None:
	key = frappe.conf.get("erpnext_api_key")
	sec = frappe.conf.get("erpnext_api_secret")
	if not key or not sec:
		return None
	return {
		"Authorization": f"token {key}:{sec}",
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _erp_get(path: str, params: dict | None = None):
	import requests
	headers = _erp_headers()
	if not headers:
		return {"error": "erpnext credentials missing"}
	r = requests.get(f"{_erp_endpoint()}{path}", headers=headers,
	                 params=params or {}, timeout=30)
	try:
		j = r.json()
	except Exception:
		j = {"raw": r.text[:500]}
	if r.status_code >= 400:
		return {"error": f"http {r.status_code}", "body": j}
	return j


def _erp_post(path: str, payload: dict):
	import requests
	headers = _erp_headers()
	if not headers:
		return {"error": "erpnext credentials missing"}
	r = requests.post(f"{_erp_endpoint()}{path}",
	                  headers=headers,
	                  data=json.dumps(payload), timeout=60)
	try:
		j = r.json()
	except Exception:
		j = {"raw": r.text[:500]}
	if r.status_code >= 400:
		return {"error": f"http {r.status_code}", "body": j}
	return j


def _erp_put(path: str, payload: dict):
	import requests
	headers = _erp_headers()
	if not headers:
		return {"error": "erpnext credentials missing"}
	r = requests.put(f"{_erp_endpoint()}{path}",
	                 headers=headers,
	                 data=json.dumps(payload), timeout=60)
	try:
		j = r.json()
	except Exception:
		j = {"raw": r.text[:500]}
	if r.status_code >= 400:
		return {"error": f"http {r.status_code}", "body": j}
	return j


# ---------- item sync ----------

def _erp_item_code(cost) -> str:
	return cost.erp_item_code or f"INFRA-{cost.cost_code}"


@frappe.whitelist()
def push_infra_item_to_erp(cost_code: str) -> dict:
	"""Upsert un Item su ERPNext per un Infrastructure Cost."""
	cost = frappe.get_doc("Infrastructure Cost", cost_code)
	item_code = _erp_item_code(cost)
	payload = {
		"item_code": item_code,
		"item_name": f"{cost.provider} · {cost.cost_code}",
		"description": cost.description or f"{cost.provider} · {cost.cost_code}",
		"item_group": "Services",
		"is_stock_item": 0,
		"is_service_item": 1,
		"include_item_in_manufacturing": 0,
		"stock_uom": "Nos",
		"standard_rate": flt(cost.monthly_cost),
		"item_defaults": [],
	}
	# Check existing
	got = _erp_get(f"/api/resource/Item/{item_code}")
	if got.get("error") and "404" not in str(got.get("error")):
		return {"error": "lookup_failed", "details": got}

	if "data" in got:
		# update
		res = _erp_put(f"/api/resource/Item/{item_code}", {
			"description": payload["description"],
			"item_name": payload["item_name"],
			"standard_rate": payload["standard_rate"],
		})
		return {"updated": item_code, "res": res}
	# create
	res = _erp_post("/api/resource/Item", payload)
	if res.get("error"):
		return {"error": "create_failed", "details": res}
	return {"created": item_code, "res": res.get("data", {}).get("name")}


@frappe.whitelist()
def push_all_infra_items_to_erp() -> dict:
	"""Sincronizza TUTTI gli Infrastructure Cost attivi come Item su ERP."""
	if not _erp_headers():
		return {"skipped": "no_credentials"}
	results = {"created": [], "updated": [], "errors": []}
	for c in frappe.get_all("Infrastructure Cost",
	                        filters={"is_active": 1, "auto_invoice_to_thanatos": 1},
	                        pluck="name"):
		r = push_infra_item_to_erp(c)
		if "created" in r:
			results["created"].append(r["created"])
		elif "updated" in r:
			results["updated"].append(r["updated"])
		else:
			results["errors"].append({"cost": c, "err": r})
	return results


# ---------- monthly Pro-Forma (Quotation) ----------
#
# Workflow:
#   1) scheduler monthly → emit_monthly_proforma_on_erp() crea una Quotation
#      su ERP (pro-forma, no fiscal value, no SDI).
#   2) Cliente paga.
#   3) Operatore (o webhook payment) chiama convert_proforma_to_invoice(quotation)
#      → crea Sales Invoice da quella quotation e la submitta.

def _resolve_customer_names() -> tuple[str, str]:
	"""(buyer, seller_company) — Thanatos è il Customer, MMOS è la Company."""
	buyer = (frappe.conf.get("erpnext_thanatos_customer")
	         or "Thanatos Investigazioni S.R.L.")
	company = (frappe.conf.get("erpnext_mmos_company")
	           or "MMOS")
	return buyer, company



def _ai_monthly_cost(month_start, markup):
	"""Aggrega AI Usage Log del mese → (billable, real_cost, log_count)."""
	from frappe.utils import get_last_day
	first = str(month_start)
	last = str(get_last_day(month_start))
	result = frappe.db.sql(
		"SELECT COALESCE(SUM(real_cost), 0), COUNT(*) FROM "tabAI Usage Log""		" WHERE usage_date BETWEEN %s AND %s",
		(first, last))
	real_total = float(result[0][0] or 0)
	count = int(result[0][1] or 0)
	ai_markup = float(frappe.conf.get("ai_markup") or markup)
	return round(real_total * ai_markup, 4), real_total, count

@frappe.whitelist()
def emit_monthly_proforma_on_erp(for_month: str | None = None) -> dict:
	"""Genera Quotation (Pro-Forma) su ERP con linee = tutti gli Infrastructure
	Cost auto-invoice per il mese specificato (default: mese precedente).
	NON crea Sales Invoice — quella si genera solo a incasso avvenuto via
	convert_proforma_to_invoice()."""
	if not _erp_headers():
		return {"skipped": "no_credentials"}

	today = now_datetime()
	if for_month:
		month_start = frappe.utils.getdate(f"{for_month}-01")
	else:
		month_start = get_first_day(add_months(today, -1))
	month_label = month_start.strftime("%Y-%m")

	costs = frappe.get_all(
		"Infrastructure Cost",
		filters={"is_active": 1, "auto_invoice_to_thanatos": 1},
		fields=["name", "cost_code", "provider", "monthly_cost", "currency",
		        "erp_item_code", "description"],
	)
	_markup = float(frappe.conf.get("infra_markup") or 3.0)
	_ai_billable, _ai_real, _ai_log_count = _ai_monthly_cost(month_start, _markup)
	if not costs and _ai_billable <= 0:
		return {"skipped": "no_costs"}

	buyer, company = _resolve_customer_names()
	po_no = f"INFRA-{month_label}"

	# Dedup: skip if Quotation already exists on ERP for this month
	existing = _erp_get("/api/resource/Quotation",
	                    params={"filters": json.dumps([
	                        ["party_name", "=", buyer],
	                        ["custom_proforma_ref", "=", po_no]])})
	# Fallback dedup via title if custom field missing
	if not existing.get("data"):
		existing = _erp_get("/api/resource/Quotation",
		                    params={"filters": json.dumps([
		                        ["party_name", "=", buyer],
		                        ["title", "=", f"PROFORMA-{po_no}"]])})
	if existing.get("data"):
		return {"already_exists": existing["data"][0]["name"],
		        "month": month_label}

	items = []
	total = 0.0
	for c in costs:
		amt = round(flt(c.monthly_cost) * _markup, 2)
		if amt <= 0:
			continue
		item_code = c.erp_item_code or f"INFRA-{c.cost_code}"
		# Make sure Item exists on ERP
		got = _erp_get(f"/api/resource/Item/{item_code}")
		if got.get("error"):
			r = push_infra_item_to_erp(c.name)
			if "error" in r:
				frappe.log_error(f"ERP item push fail {item_code}: {r}",
				                 "erp_sync")
				continue
		items.append({
			"item_code": item_code,
			"qty": 1,
			"rate": amt,
			"description": f"{c.provider} · {c.cost_code} · {month_label}",
		})
		total += amt

	# AI Usage line item
	if _ai_billable > 0:
		_ai_item = "AI-USAGE"
		if _erp_get(f"/api/resource/Item/{_ai_item}").get("error"):
			_erp_post("/api/resource/Item", {
				"item_code": _ai_item,
				"item_name": "AI Usage (Thanatos)",
				"item_group": "Services",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_service_item": 1,
			})
		items.append({
			"item_code": _ai_item,
			"qty": 1,
			"rate": _ai_billable,
			"description": f"AI Usage Thanatos {month_label} — {_ai_log_count} log, costo reale MMOS €{_ai_real:.4f}",
		})
		total += _ai_billable

	# Deduzione quota infra gia trattenuta per-transazione (cap 20% netto) nelle RD del mese
	try:
		from frappe.utils import getdate, get_first_day, get_last_day
		_first = get_first_day(getdate(month_label + "-01"))
		_last = get_last_day(_first)
		collected = float(frappe.db.sql(
			"SELECT COALESCE(SUM(infra_cost_share),0) FROM `tabRevenue Distribution` "
			"WHERE DATE(creation) BETWEEN %s AND %s", (_first, _last))[0][0] or 0)
	except Exception:
		collected = 0.0
	if items and collected > 0:
		acc_item = "INFRA-ACCONTO"
		if _erp_get("/api/resource/Item/%s" % acc_item).get("error"):
			_erp_post("/api/resource/Item", {"item_code": acc_item,
				"item_name": "Acconto quota infra (cap 20%)", "item_group": "Services",
				"stock_uom": "Nos", "is_stock_item": 0, "is_service_item": 1})
		items.append({"item_code": acc_item, "qty": 1, "rate": -round(collected, 2),
			"description": "Quota infra gia trattenuta (cap 20%) - %s" % month_label})
		total = round(total - collected, 2)

	if not items:
		return {"skipped": "all_zero"}

	# Italian region requires at least one Tax row.
	# We prefer a "Reverse Charge EU" template if it exists, else fall back
	# to the configured default or the first Italy VAT 22% template.
	tax_template = frappe.conf.get("erpnext_tax_template")
	if not tax_template:
		tx = _erp_get("/api/resource/Sales Taxes and Charges Template",
		              params={"limit_page_length": 50,
		                      "fields": '["name","title"]'})
		choices = [t.get("name", "") for t in (tx.get("data") or [])]
		for needle in ("Reverse Charge", "Esente", "Italy VAT 22"):
			match = next((c for c in choices if needle.lower() in c.lower()), None)
			if match:
				tax_template = match
				break

	payload = {
		"quotation_to": "Customer",
		"party_name": buyer,
		"customer": buyer,
		"company": company,
		"transaction_date": str(get_last_day(month_start)),
		"valid_till": str(get_last_day(add_months(month_start, 1))),
		"order_type": "Sales",
		"title": f"PROFORMA-{po_no}",
		"currency": (costs[0].currency or "EUR"),
		"tc_name": None,
		"terms": (f"Pro-Forma Infrastruttura Thanatos {month_label}.\n"
		          f"Fattura emessa ad incasso avvenuto. "
		          f"Riferimento contabile: {po_no}."),
		"items": items,
	}
	if tax_template:
		payload["taxes_and_charges"] = tax_template
		tpl = _erp_get(f"/api/resource/Sales Taxes and Charges Template/{tax_template}")
		tpl_data = tpl.get("data") or {}
		tax_rows = []
		for t in tpl_data.get("taxes", []):
			row = {
				"charge_type": t.get("charge_type"),
				"account_head": t.get("account_head"),
				"rate": t.get("rate") or 0,
				"description": t.get("description"),
				"cost_center": t.get("cost_center"),
			}
			if t.get("tax_amount"):
				row["tax_amount"] = t["tax_amount"]
			tax_rows.append(row)
		if tax_rows:
			payload["taxes"] = tax_rows
	r = _erp_post("/api/resource/Quotation", payload)
	if r.get("error"):
		frappe.log_error(f"ERP Quotation create fail: {r}", "erp_sync")
		return {"error": "create_failed", "details": r}
	name = (r.get("data") or {}).get("name")
	return {"proforma": name, "total": round(total, 2),
	        "items": len(items), "month": month_label,
	        "po_no": po_no,
	        "next_step": "Quando incassi: chiama convert_proforma_to_invoice('"+(name or "")+"')"}


# Backwards-compat alias (some external callers may still use the old name)
@frappe.whitelist()
def emit_monthly_invoice_on_erp(for_month: str | None = None) -> dict:
	"""DEPRECATED: alias di emit_monthly_proforma_on_erp().
	Mantenuto per backward-compat — ora emette Pro-Forma, non Sales Invoice."""
	return emit_monthly_proforma_on_erp(for_month)


# ---------- convert pro-forma → invoice on payment ----------

@frappe.whitelist()
def convert_proforma_to_invoice(quotation_name: str, submit: bool = True) -> dict:
	"""Converte una Quotation (pro-forma) in Sales Invoice e (opzionalmente)
	la submitta. Da chiamare a incasso avvenuto."""
	if not _erp_headers():
		return {"skipped": "no_credentials"}

	q = _erp_get(f"/api/resource/Quotation/{quotation_name}")
	if q.get("error") or not q.get("data"):
		return {"error": "quotation_not_found",
		        "quotation": quotation_name, "details": q}
	qd = q["data"]

	# Build Sales Invoice from quotation
	items = []
	for it in qd.get("items", []):
		items.append({
			"item_code": it.get("item_code"),
			"qty": it.get("qty"),
			"rate": it.get("rate"),
			"description": it.get("description"),
		})

	po_no = (qd.get("title") or "").replace("PROFORMA-", "")
	payload = {
		"customer": qd.get("party_name") or qd.get("customer"),
		"company": qd.get("company"),
		"posting_date": str(frappe.utils.today()),
		"due_date": str(frappe.utils.today()),
		"po_no": po_no,
		"po_date": qd.get("transaction_date"),
		"currency": qd.get("currency") or "EUR",
		"remarks": f"Fattura da Pro-Forma {quotation_name} - incasso ricevuto",
		"items": items,
	}
	if qd.get("taxes_and_charges"):
		payload["taxes_and_charges"] = qd["taxes_and_charges"]
		tax_rows = []
		for t in qd.get("taxes", []):
			row = {
				"charge_type": t.get("charge_type"),
				"account_head": t.get("account_head"),
				"rate": t.get("rate") or 0,
				"description": t.get("description"),
				"cost_center": t.get("cost_center"),
			}
			if t.get("tax_amount"):
				row["tax_amount"] = t["tax_amount"]
			tax_rows.append(row)
		if tax_rows:
			payload["taxes"] = tax_rows

	r = _erp_post("/api/resource/Sales Invoice", payload)
	if r.get("error"):
		return {"error": "create_failed", "details": r}
	inv_name = (r.get("data") or {}).get("name")

	if submit and inv_name:
		# Submit the Sales Invoice via /api/method
		sub = _erp_post("/api/method/frappe.client.submit",
		                {"doc": json.dumps({"doctype": "Sales Invoice",
		                                    "name": inv_name})})
		# best-effort: also link Quotation → Sales Invoice via status update
		_erp_put(f"/api/resource/Quotation/{quotation_name}",
		         {"status": "Ordered"})
		return {"invoice": inv_name, "submitted": True,
		        "from_proforma": quotation_name}

	return {"invoice": inv_name, "submitted": False,
	        "from_proforma": quotation_name}


# ---------- scheduler hooks ----------

def scheduled_monthly_invoice_on_erp():
	"""Hook scheduler_events.monthly: emette la Pro-Forma MMOS→Thanatos
	il primo del mese (per il mese precedente)."""
	try:
		res = emit_monthly_proforma_on_erp()
		frappe.logger().info(f"[erp_sync] monthly proforma: {res}")
	except Exception:
		frappe.log_error(frappe.get_traceback(),
		                 "erp_sync monthly proforma")


# ---------- client stripe invoice → ERP Sales Invoice ----------

def _erp_ensure_client_customer(client_name: str) -> str | None:
	"""Trova o crea il Customer su ERPNext per un Investigation Client.
	Usa erp_customer_id come cache. Ritorna il nome Customer su ERP."""
	if not _erp_headers():
		return None

	cached = frappe.db.get_value("Investigation Client", client_name, "erp_customer_id")
	if cached:
		got = _erp_get(f"/api/resource/Customer/{cached}")
		if got.get("data"):
			return cached

	client = frappe.get_doc("Investigation Client", client_name)
	customer_name = client.client_name or client_name

	existing = _erp_get("/api/resource/Customer",
	                    params={"filters": json.dumps([["customer_name", "=", customer_name]]),
	                            "limit": 1})
	if existing.get("data"):
		erp_name = existing["data"][0]["name"]
		frappe.db.set_value("Investigation Client", client_name, "erp_customer_id", erp_name,
		                    update_modified=False)
		frappe.db.commit()
		return erp_name

	ctype = "Individual" if (client.client_type or "Individual") == "Individual" else "Company"
	r = _erp_post("/api/resource/Customer", {
		"customer_name": customer_name,
		"customer_type": ctype,
		"customer_group": "All Customer Groups",
		"territory": client.country or "All Territories",
		"email_id": client.email or "",
		"mobile_no": client.phone or "",
		"tax_id": client.vat_number or "",
	})
	if r.get("error"):
		frappe.log_error(f"ERP Customer create fail {client_name}: {r}", "erp_sync_client")
		return None
	erp_name = (r.get("data") or {}).get("name")
	if erp_name:
		frappe.db.set_value("Investigation Client", client_name, "erp_customer_id", erp_name,
		                    update_modified=False)
		frappe.db.commit()
	return erp_name


def _erp_seller_company() -> str:
	return (frappe.conf.get("erpnext_seller_company")
	        or frappe.conf.get("erpnext_mmos_company")
	        or "Michele Milazzo")


def _ensure_thanatos_item(item_code: str, item_name: str):
	"""Crea l'Item su ERP se non esiste."""
	if not _erp_get(f"/api/resource/Item/{item_code}").get("error"):
		return
	_erp_post("/api/resource/Item", {
		"item_code": item_code,
		"item_name": item_name,
		"item_group": "Services",
		"stock_uom": "Nos",
		"is_stock_item": 0,
		"is_service_item": 1,
	})


@frappe.whitelist()
def sync_client_stripe_invoice_to_erp(stripe_invoice: dict) -> dict:
	"""Dopo stripe invoice.paid: crea Sales Invoice su ERPNext per il cliente.
	Idempotente: se già esiste (po_no = stripe invoice id) skippa.

	La Sales Invoice usa come Company il seller configurato (erpnext_seller_company,
	default 'Michele Milazzo') e come Customer l'Investigation Client trovato via
	stripe_customer_id.
	"""
	if not _erp_headers():
		return {"skipped": "no_credentials"}

	stripe_inv_id = stripe_invoice.get("id") if isinstance(stripe_invoice, dict) else getattr(stripe_invoice, "id", None)
	if not stripe_inv_id:
		return {"skipped": "no_invoice_id"}

	existing = _erp_get("/api/resource/Sales Invoice",
	                    params={"filters": json.dumps([["po_no", "=", stripe_inv_id]]),
	                            "limit": 1})
	if existing.get("data"):
		return {"already_exists": existing["data"][0]["name"]}

	customer_id = stripe_invoice.get("customer") if isinstance(stripe_invoice, dict) else getattr(stripe_invoice, "customer", None)
	client_name = frappe.db.get_value("Investigation Client",
	                                  {"stripe_customer_id": customer_id}, "name")
	if not client_name:
		return {"skipped": "client_not_found", "stripe_customer": customer_id}

	erp_customer = _erp_ensure_client_customer(client_name)
	if not erp_customer:
		return {"error": "customer_create_failed", "client": client_name}

	# Righe da Stripe invoice lines
	stripe_lines = ((stripe_invoice.get("lines") or {}).get("data") or []) if isinstance(stripe_invoice, dict) else []
	items = []
	for line in stripe_lines:
		desc = line.get("description") or "Thanatos Intel — Abbonamento"
		amt = (line.get("amount") or 0) / 100.0
		if amt == 0:
			continue
		item_code = "THANATOS-SUB"
		_ensure_thanatos_item(item_code, "Thanatos Intel — Abbonamento")
		items.append({"item_code": item_code, "qty": 1, "rate": amt,
		              "description": desc[:140]})

	if not items:
		total = ((stripe_invoice.get("amount_paid") or 0) / 100.0 if isinstance(stripe_invoice, dict)
		         else getattr(stripe_invoice, "amount_paid", 0) / 100.0)
		if total <= 0:
			return {"skipped": "zero_amount"}
		item_code = "THANATOS-SUB"
		_ensure_thanatos_item(item_code, "Thanatos Intel — Abbonamento")
		items.append({"item_code": item_code, "qty": 1, "rate": total,
		              "description": f"Stripe Invoice {stripe_inv_id}"})

	currency = ((stripe_invoice.get("currency") or "eur").upper() if isinstance(stripe_invoice, dict)
	            else getattr(stripe_invoice, "currency", "eur").upper())
	hosted_url = (stripe_invoice.get("hosted_invoice_url") or "") if isinstance(stripe_invoice, dict) else ""

	payload = {
		"customer": erp_customer,
		"company": _erp_seller_company(),
		"posting_date": str(frappe.utils.today()),
		"due_date": str(frappe.utils.today()),
		"po_no": stripe_inv_id,
		"currency": currency,
		"remarks": f"Stripe Invoice {stripe_inv_id}" + (f" — {hosted_url}" if hosted_url else ""),
		"items": items,
		"is_pos": 0,
	}

	r = _erp_post("/api/resource/Sales Invoice", payload)
	if r.get("error"):
		frappe.log_error(f"ERP Sales Invoice create fail: {r}", "erp_sync_client")
		return {"error": "create_failed", "details": r}

	inv_name = (r.get("data") or {}).get("name")
	if inv_name:
		try:
			_erp_post("/api/method/frappe.client.submit",
			          {"doc": json.dumps({"doctype": "Sales Invoice", "name": inv_name})})
		except Exception:
			pass

	frappe.log_error(f"ERP Sales Invoice created: {inv_name} for {client_name}", "erp_sync_client_ok")
	return {"invoice": inv_name, "client": client_name,
	        "stripe_invoice": stripe_inv_id, "erp_customer": erp_customer}


@frappe.whitelist()
def invite_accountant_to_erp(email: str, full_name: str) -> dict:
	"""Crea un utente ERPNext con ruolo 'Accounts User' per il commercialista.
	Può essere chiamato dall'admin Thanatos per dare accesso in sola lettura contabile.
	L'utente riceve un'email di invito dal sito ERP."""
	if not _erp_headers():
		return {"skipped": "no_credentials"}

	# Check se l'utente esiste già su ERP
	existing = _erp_get(f"/api/resource/User/{email}")
	if existing.get("data"):
		return {"already_exists": email, "erp_url": _erp_endpoint() + "/app/user/" + email}

	r = _erp_post("/api/resource/User", {
		"email": email,
		"full_name": full_name,
		"send_welcome_email": 1,
		"enabled": 1,
		"roles": [
			{"role": "Accounts User"},
			{"role": "Report User"},
		],
	})
	if r.get("error"):
		frappe.log_error(f"ERP User create fail {email}: {r}", "erp_invite_accountant")
		return {"error": "create_failed", "details": r}

	name = (r.get("data") or {}).get("name")
	return {"created": name, "email": email,
	        "erp_url": _erp_endpoint() + "/app",
	        "note": "L'utente riceve un'email di invito da erp.onekeyco.com"}


def on_infrastructure_cost_save(doc, method=None):
	"""Hook doc_events: appena Infrastructure Cost viene salvato,
	pusha l'Item su ERP (best-effort)."""
	if not doc.is_active or not doc.auto_invoice_to_thanatos:
		return
	if not _erp_headers():
		return
	try:
		push_infra_item_to_erp(doc.name)
	except Exception:
		frappe.log_error(frappe.get_traceback(),
		                 "erp_sync on_infra_save")
