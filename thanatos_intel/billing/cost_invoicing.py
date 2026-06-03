"""
Auto-fatturazione mensile: MMOS / OneKeyCo emette fattura ERPNext verso Thanatos
per ricaricare i costi infrastrutturali (Hetzner, Claude, Codex, OpenRouter, OpenCode...).
"""
import frappe
from frappe.utils import now_datetime, get_first_day, get_last_day, add_months


@frappe.whitelist()
def emit_monthly_cost_invoice(for_month: str = None) -> dict:
    """Genera una Sales Invoice ERPNext con linee = tutti gli Infrastructure Cost auto_invoice."""
    today = now_datetime()
    if for_month:
        month_start = frappe.utils.getdate(f"{for_month}-01")
    else:
        month_start = get_first_day(add_months(today, -1))
    month_label = month_start.strftime("%Y-%m")

    costs = frappe.get_all("Infrastructure Cost",
                           filters={"is_active": 1, "auto_invoice_to_thanatos": 1},
                           fields=["name", "cost_code", "provider", "monthly_cost",
                                   "currency", "erp_item_code", "description"])
    if not costs:
        return {"skipped": "no_active_costs"}

    customer_name = frappe.conf.get("thanatos_invoice_customer") or "Thanatos Agency"
    try:
        if not frappe.db.exists("Customer", customer_name):
            from thanatos_intel.integrations.erpnext_billing import _pick_leaf
            cg = _pick_leaf("Customer Group")
            tt = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
            cust = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": customer_name,
                "customer_type": "Company",
                "customer_group": cg,
                "territory": tt,
            })
            cust.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "MMOS→Thanatos customer create")

    if frappe.db.exists("Sales Invoice", {"po_no": f"INFRA-{month_label}",
                                          "customer": customer_name}):
        existing = frappe.db.get_value("Sales Invoice",
                                       {"po_no": f"INFRA-{month_label}",
                                        "customer": customer_name}, "name")
        return {"already_exists": existing}

    items = []
    total = 0.0
    for c in costs:
        if float(c.monthly_cost or 0) <= 0:
            continue
        item_code = c.erp_item_code or f"INFRA-{c.cost_code}"
        if not frappe.db.exists("Item", item_code):
            try:
                from thanatos_intel.integrations.erpnext_billing import get_or_create_item
                # creiamo un fake service item per la riga
                item = frappe.get_doc({
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": f"{c.provider} · {c.cost_code}",
                    "item_group": "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups",
                    "stock_uom": "Nos",
                    "is_stock_item": 0,
                    "include_item_in_manufacturing": 0,
                    "is_service_item": 1,
                    "description": c.description or c.provider,
                })
                item.insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "infra item create")
                continue
        items.append({
            "item_code": item_code,
            "qty": 1,
            "rate": float(c.monthly_cost),
            "description": f"{c.provider} · {c.cost_code} · {month_label}",
        })
        total += float(c.monthly_cost)

    if not items:
        return {"skipped": "no_items"}

    try:
        si = frappe.get_doc({
            "doctype": "Sales Invoice",
            "customer": customer_name,
            "posting_date": get_last_day(month_start),
            "due_date": get_last_day(add_months(month_start, 1)),
            "po_no": f"INFRA-{month_label}",
            "po_date": get_first_day(month_start),
            "remarks": f"Costi infrastruttura {month_label}",
            "items": items,
        })
        si.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"invoice": si.name, "total": total, "items": len(items), "month": month_label}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "MMOS→Thanatos SI create")
        return {"error": str(e)[:300]}


@frappe.whitelist()
def scheduled_monthly_cost_invoicing():
    """Hook scheduler_events.monthly: emette la fattura del mese precedente."""
    try:
        emit_monthly_cost_invoice()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "monthly cost invoicing")
