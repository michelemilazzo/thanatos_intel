"""Settlement mensile dei clienti a credito concesso (fatturazione a bonifico).

I servizi automatizzati dei clienti con `credit_granted` non sono prepagati a carta:
scalano dal fido (service_credit puo andare negativo fino a credit_limit). Questo
modulo, a inizio mese, emette una Sales Invoice (bozza, pagamento a bonifico) con il
consumato del mese precedente e azzera il contatore del fido.

- Posticipata: fattura a fine periodo, scadenza a fine mese corrente.
- Anticipata:  fattura subito a inizio periodo, scadenza immediata.

La fattura nasce in BOZZA: l'operatore la verifica e la invia. Idempotente per mese
(non rifattura un periodo gia coperto).
"""
import frappe
from frappe.utils import flt, getdate, get_first_day, get_last_day, add_months, add_days, today, now_datetime

from thanatos_intel.billing.internal_invoicing import ensure_customer_for_client

SETTLE_ITEM = "SVC-CREDIT-SETTLEMENT"


def _ensure_item():
    if frappe.db.exists("Item", SETTLE_ITEM):
        return SETTLE_ITEM
    group = (frappe.db.get_value("Item Group", {"item_group_name": "Services"}, "name")
             or frappe.db.get_value("Item Group", {"is_group": 0}, "name"))
    frappe.get_doc({
        "doctype": "Item", "item_code": SETTLE_ITEM, "item_name": "Servizi automatizzati a credito",
        "item_group": group, "is_stock_item": 0, "is_sales_item": 1,
        "stock_uom": "Nos", "description": "Consumo mensile servizi automatizzati (cliente a credito)",
    }).insert(ignore_permissions=True)
    return SETTLE_ITEM


def _period_spend(client, start, end):
    rows = frappe.get_all("Credit Ledger",
        filters={"client": client, "kind": "Spent", "creation": ["between", [str(start), str(end) + " 23:59:59"]]},
        fields=["amount"])
    return sum(flt(r.amount) for r in rows)


def _recurring_lines(client):
    """Canoni ricorrenti del cliente a credito: abbonamento attivo + add-on attivi."""
    lines = []
    sub = frappe.db.get_value("Investigation Client", client,
                              ["subscription_plan", "subscription_status"], as_dict=True) or {}
    if sub.get("subscription_status") == "Active" and sub.get("subscription_plan"):
        mp = flt(frappe.db.get_value("Investigation Subscription Plan", sub.subscription_plan, "monthly_price"))
        if mp:
            lines.append(("Abbonamento %s" % sub.subscription_plan, mp))
    addons = (frappe.db.get_value("Investigation Client", client, "active_addons") or "")
    for code in [a.strip() for a in addons.split(",") if a.strip()]:
        row = frappe.db.get_value("Service Catalog", {"service_code": code},
                                  ["service_name", "price"], as_dict=True)
        if row and row.price:
            lines.append((row.service_name, flt(row.price)))
    return lines


def settle_client(client, start, end, terms_label, due_date):
    """Crea la fattura bozza del periodo [start, end] (consumo pay-per-use + canoni
    ricorrenti) e azzera il fido. Idempotente per periodo."""
    period_tag = "credit-settle:%s:%s" % (client, start)
    if frappe.db.exists("Credit Ledger", {"kind": "Adjustment", "reference_name": period_tag}):
        return None
    spent = _period_spend(client, start, end)
    rec = _recurring_lines(client)
    if spent <= 0 and not rec:
        return None
    customer = ensure_customer_for_client(client)
    item = _ensure_item()
    items = []
    if spent > 0:
        items.append({"item_code": item, "qty": 1, "rate": flt(spent),
                      "description": "Servizi automatizzati (pay-per-use) — %s" % terms_label})
    for label, amount in rec:
        items.append({"item_code": item, "qty": 1, "rate": flt(amount),
                      "description": "%s — %s" % (label, terms_label)})
    inv = frappe.get_doc({
        "doctype": "Sales Invoice", "customer": customer, "currency": "EUR",
        "set_posting_time": 1, "due_date": str(due_date),
        "items": items,
        "terms": ("Servizi del periodo %s.\n"
                  "Pagamento a BONIFICO bancario (cliente a credito concesso).\n"
                  "THANATOS INVESTIGAZIONI S.R.L." % terms_label),
    })
    inv.insert(ignore_permissions=True)  # resta in BOZZA per revisione operatore

    # azzera il contatore del fido per il nuovo periodo + traccia a ledger (idempotenza)
    bal = flt(frappe.db.get_value("Investigation Client", client, "service_credit"))
    frappe.db.set_value("Investigation Client", client, "service_credit", flt(bal + spent), update_modified=False)
    frappe.get_doc({
        "doctype": "Credit Ledger", "party_type": "Client", "party": client, "client": client,
        "kind": "Adjustment", "amount": flt(spent), "balance_after": flt(bal + spent),
        "reference_doctype": "Sales Invoice", "reference_name": period_tag,
        "notes": "Settlement mensile a bonifico %s → fattura %s" % (terms_label, inv.name),
    }).insert(ignore_permissions=True)
    return inv.name


def run_monthly_credit_settlement():
    """Schedulata (monthly, a inizio mese): fattura il mese precedente ai clienti a credito.
    Anticipata e posticipata fatturano lo stesso consumato; cambia la scadenza."""
    prev = add_months(get_first_day(today()), -1)
    start, end = get_first_day(prev), get_last_day(prev)
    label = getdate(prev).strftime("%m/%Y")
    clients = frappe.get_all("Investigation Client", filters={"credit_granted": 1},
                             fields=["name", "credit_terms"])
    done = []
    for c in clients:
        try:
            if (c.credit_terms or "") == "Posticipata":
                due = get_last_day(today())      # scadenza a fine mese corrente
            else:                                 # Anticipata (o non specificato)
                due = add_days(today(), 7)        # scadenza immediata (7 gg)
            inv = settle_client(c.name, start, end, label, due)
            if inv:
                done.append((c.name, inv))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "credit settlement " + c.name)
    frappe.db.commit()
    return {"period": label, "invoiced": len(done), "clients": done}
