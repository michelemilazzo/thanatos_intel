"""Thanatos Internal Billing — fatturazione clienti DENTRO Thanatos.

Usa l'ERPNext LOCALE installato su thanatos.onekeyco.com (stesso bench).
Differente da erp_sync.py che parla con erp.onekeyco.com (book-keeping
OneKeyCo, dove finiscono solo i costi infra + fee dovuti a OneKeyCo da
Thanatos).

Mappa Thanatos → ERPNext locale:
  Investigation Client   →  Customer
  Service Catalog item   →  Item
  Investigation Case     →  Quotation → Sales Order → Sales Invoice
  Investigation Report   →  delivery trigger
  Pay-per-use checkout   →  Stripe Payment Entry diretto

Tutti i record vivono nel DB del sito thanatos.onekeyco.com (zero rete).
"""
from __future__ import annotations
import frappe
from frappe.utils import flt, now_datetime


# ---------------------------------------------------------------------------
# Customer mapping
# ---------------------------------------------------------------------------

def ensure_customer_for_client(client_name: str) -> str:
    """Crea (idempotente) il record Customer ERPNext per un Investigation Client."""
    c = frappe.get_doc("Investigation Client", client_name)
    cust_id = c.get("local_erpnext_customer") or None

    if cust_id and frappe.db.exists("Customer", cust_id):
        return cust_id

    # search by email
    existing = frappe.db.get_value("Customer",
        {"customer_primary_address": c.email}, "name") if c.email else None
    if not existing:
        existing = frappe.db.get_value("Customer",
            {"customer_name": c.client_name}, "name")

    if existing:
        cust_id = existing
    else:
        cust_id = _create_customer(c)

    # store back-ref (avoid Link required if field missing)
    try:
        if hasattr(c, "local_erpnext_customer"):
            c.db_set("local_erpnext_customer", cust_id, commit=True)
    except Exception:
        pass
    return cust_id


def _create_customer(c) -> str:
    type_map = {
        "Individual":      "Individual",
        "Company":         "Company",
        "Law Firm":        "Company",
        "Accounting Firm": "Company",
        "Other":           "Company",
    }
    territory_map = {"Italy": "Italy", "Romania": "Romania"}
    cust = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": c.client_name,
        "customer_type": type_map.get(c.client_type, "Company"),
        "customer_group": "All Customer Groups",
        "territory": territory_map.get(c.country, "All Territories"),
        "tax_id": c.vat_number or None,
        "language": {"Italian": "it", "English": "en", "Romanian": "ro"}.get(
            c.preferred_language, "en"),
    })
    cust.insert(ignore_permissions=True)
    frappe.db.commit()
    return cust.name


# ---------------------------------------------------------------------------
# Item mapping (Service Catalog → ERPNext Item)
# ---------------------------------------------------------------------------

def ensure_item_for_service(service_code: str) -> str:
    """Crea (idempotente) il record Item per un Service Catalog code."""
    if frappe.db.exists("Item", service_code):
        return service_code
    svc = frappe.get_doc("Service Catalog", {"service_code": service_code})
    item = frappe.get_doc({
        "doctype": "Item",
        "item_code": service_code,
        "item_name": svc.service_name[:140],
        "item_group": "Services",
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "is_service_item": 1,
        "include_item_in_manufacturing": 0,
        "standard_rate": flt(svc.price or (svc.price_min + svc.price_max) / 2
                              if svc.price_min and svc.price_max else 0),
        "description": svc.description or svc.service_name,
    })
    item.insert(ignore_permissions=True)
    frappe.db.commit()
    return service_code


# ---------------------------------------------------------------------------
# Quotation / Sales Order / Invoice
# ---------------------------------------------------------------------------

def create_quotation_for_case(case_name: str,
                              service_codes: list[str] | None = None) -> str:
    """Crea una Quotation ERPNext locale per un Investigation Case.

    Args:
      case_name: nome del Investigation Case
      service_codes: lista codici Service Catalog (default: tutti i servizi del caso)
    Returns:
      name della Quotation creata
    """
    case = frappe.get_doc("Investigation Case", case_name)
    client_name = case.client
    if not client_name:
        frappe.throw("Caso senza cliente associato.")

    customer = ensure_customer_for_client(client_name)

    # fallback: se non specificato, prova a leggere da case.requested_services
    # (child table o str campo). Se vuoto: niente quotation.
    if not service_codes:
        codes = []
        if hasattr(case, "requested_services") and case.requested_services:
            for ln in case.requested_services:
                if hasattr(ln, "service_code"):
                    codes.append(ln.service_code)
        service_codes = codes
    if not service_codes:
        frappe.throw("Nessun servizio specificato per la quotation.")

    items = []
    for code in service_codes:
        ensure_item_for_service(code)
        svc = frappe.get_doc("Service Catalog", {"service_code": code})
        rate = flt(svc.price or
                   ((svc.price_min + svc.price_max) / 2
                    if svc.price_min and svc.price_max else svc.price_min or 0))
        items.append({
            "item_code": code,
            "qty": 1,
            "rate": rate,
            "description": svc.service_name,
        })

    quotation = frappe.get_doc({
        "doctype": "Quotation",
        "quotation_to": "Customer",
        "party_name": customer,
        "customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
        "currency": "EUR",
        "transaction_date": now_datetime().date(),
        "valid_till": frappe.utils.add_days(now_datetime().date(), 30),
        "items": items,
        "tc_name": None,
        "terms": (
            "Pagamento sicuro Stripe (carta o bonifico).\n"
            "Validità offerta: 30 giorni.\n"
            "Servizi erogati da THANATOS INVESTIGAZIONI S.R.L. — CUI RO 46901022.\n"
            "Diritto applicabile: diritto romeno. Foro competente: Tribunalul Constanța."
        ),
    })
    quotation.insert(ignore_permissions=True)
    frappe.db.commit()

    # Audit + back-link to case
    try:
        if hasattr(case, "quotation"):
            case.db_set("quotation", quotation.name, commit=True)
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": "billing.quotation_created",
            "new_value": quotation.name,
            "reason": frappe.as_json({
                "case": case_name, "customer": customer,
                "services": service_codes,
                "total": quotation.grand_total,
            })[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return quotation.name


def quotation_to_sales_order(quotation_name: str) -> str:
    """Quotation accepted → Sales Order (per delivery tracking)."""
    from erpnext.selling.doctype.quotation.quotation import make_sales_order
    so = make_sales_order(quotation_name)
    so.insert(ignore_permissions=True)
    so.submit()
    frappe.db.commit()
    return so.name


def sales_order_to_invoice(sales_order_name: str) -> str:
    """Sales Order delivered → Sales Invoice."""
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    inv = make_sales_invoice(sales_order_name)
    inv.insert(ignore_permissions=True)
    frappe.db.commit()
    return inv.name


# ---------------------------------------------------------------------------
# Pay-per-use direct invoice
# ---------------------------------------------------------------------------

@frappe.whitelist()
def invoice_pay_per_use_purchase(client_name: str, service_code: str,
                                 stripe_payment_intent: str | None = None,
                                 amount: float | None = None) -> dict:
    """Quando un cliente compra un servizio pay-per-use via /pay-per-use:
    1. Stripe pagamento già processato (webhook)
    2. Creo direttamente Sales Invoice (no quotation/SO intermedi)
    3. Mark paid se Stripe ha confirm.
    """
    customer = ensure_customer_for_client(client_name)
    ensure_item_for_service(service_code)
    svc = frappe.get_doc("Service Catalog", {"service_code": service_code})
    rate = flt(amount or svc.price or
               ((svc.price_min + svc.price_max) / 2
                if svc.price_min and svc.price_max else 0))

    inv = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": customer,
        "currency": "EUR",
        "due_date": now_datetime().date(),
        "items": [{
            "item_code": service_code,
            "qty": 1, "rate": rate,
            "description": svc.service_name,
        }],
        "terms": (
            f"Servizio: {svc.service_name} ({service_code}).\n"
            f"Pagamento ricevuto via Stripe."
            f"{' Stripe PaymentIntent: ' + stripe_payment_intent if stripe_payment_intent else ''}\n"
            f"THANATOS INVESTIGAZIONI S.R.L. — CUI RO 46901022."
        ),
    })
    inv.insert(ignore_permissions=True)
    inv.submit()

    if stripe_payment_intent:
        try:
            pe = frappe.get_doc({
                "doctype": "Payment Entry",
                "payment_type": "Receive",
                "party_type": "Customer",
                "party": customer,
                "paid_amount": rate,
                "received_amount": rate,
                "paid_to": frappe.db.get_value("Company",
                    frappe.defaults.get_user_default("company"),
                    "default_bank_account") or "Bank Account - TH",
                "references": [{
                    "reference_doctype": "Sales Invoice",
                    "reference_name": inv.name,
                    "allocated_amount": rate,
                }],
                "reference_no": stripe_payment_intent,
                "reference_date": now_datetime().date(),
            })
            pe.insert(ignore_permissions=True)
            pe.submit()
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "invoice_pay_per_use payment entry")

    try:
        frappe.get_doc({
            "doctype": "Diplomatic Audit Log",
            "event_type": "billing.ppu_invoice_created",
            "new_value": inv.name,
            "reason": frappe.as_json({
                "client": client_name, "customer": customer,
                "service": service_code, "amount": rate,
                "stripe_payment_intent": stripe_payment_intent,
            })[:500],
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass

    return {"ok": True, "invoice": inv.name, "amount": rate}
