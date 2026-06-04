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


# ---------- monthly Sales Invoice ----------

def _resolve_customer_names() -> tuple[str, str]:
	"""(buyer, seller_company) — Thanatos è il Customer, MMOS è la Company."""
	buyer = (frappe.conf.get("erpnext_thanatos_customer")
	         or "Thanatos Investigazioni S.R.L.")
	company = (frappe.conf.get("erpnext_mmos_company")
	           or "MMOS")
	return buyer, company


@frappe.whitelist()
def emit_monthly_invoice_on_erp(for_month: str | None = None) -> dict:
	"""Genera Sales Invoice su ERP con linee = tutti gli Infrastructure Cost auto-invoice
	per il mese specificato (default: mese precedente)."""
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
	if not costs:
		return {"skipped": "no_costs"}

	buyer, company = _resolve_customer_names()
	po_no = f"INFRA-{month_label}"

	# Dedup: skip if invoice already exists on ERP
	existing = _erp_get("/api/resource/Sales Invoice",
	                    params={"filters": json.dumps([
	                        ["po_no", "=", po_no], ["customer", "=", buyer]])})
	if existing.get("data"):
		return {"already_exists": existing["data"][0]["name"],
		        "month": month_label}

	items = []
	total = 0.0
	for c in costs:
		amt = flt(c.monthly_cost)
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
		"customer": buyer,
		"company": company,
		"posting_date": str(get_last_day(month_start)),
		"due_date": str(get_last_day(add_months(month_start, 1))),
		"po_no": po_no,
		"po_date": str(month_start),
		"currency": (costs[0].currency or "EUR"),
		"remarks": f"Costi infrastruttura Thanatos {month_label}",
		"items": items,
	}
	if tax_template:
		payload["taxes_and_charges"] = tax_template
		tpl = _erp_get(f"/api/resource/Sales Taxes and Charges Template/{tax_template}")
		tpl_data = tpl.get("data") or {}
		tax_rows = []
		for t in tpl_data.get("taxes", []):
			tax_rows.append({
				"charge_type": t.get("charge_type"),
				"account_head": t.get("account_head"),
				"rate": t.get("rate"),
				"description": t.get("description"),
				"cost_center": t.get("cost_center"),
			})
		if tax_rows:
			payload["taxes"] = tax_rows
	r = _erp_post("/api/resource/Sales Invoice", payload)
	if r.get("error"):
		frappe.log_error(f"ERP SI create fail: {r}", "erp_sync")
		return {"error": "create_failed", "details": r}
	name = (r.get("data") or {}).get("name")
	return {"invoice": name, "total": round(total, 2),
	        "items": len(items), "month": month_label}


# ---------- scheduler hooks ----------

def scheduled_monthly_invoice_on_erp():
	"""Hook scheduler_events.monthly: emette la fattura MMOS→Thanatos
	il primo del mese (per il mese precedente)."""
	try:
		res = emit_monthly_invoice_on_erp()
		frappe.logger().info(f"[erp_sync] monthly invoice: {res}")
	except Exception:
		frappe.log_error(frappe.get_traceback(),
		                 "erp_sync monthly invoice")


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
