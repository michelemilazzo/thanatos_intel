"""Wallet credito servizi del cliente (bonus segnalazioni, spesa su interrogazioni)."""
import frappe
from frappe.utils import flt, get_first_day, today


def get_balance(client):
    return flt(frappe.db.get_value("Investigation Client", client, "service_credit"))


def _post(client, kind, amount, ref_dt=None, ref_name=None, notes=None):
    amount = flt(amount)
    bal = get_balance(client)
    delta = amount if kind == "Earned" else (-amount if kind == "Spent" else amount)
    new_bal = flt(bal + delta)
    frappe.get_doc({
        "doctype": "Credit Ledger", "client": client, "kind": kind, "amount": abs(amount),
        "balance_after": new_bal, "reference_doctype": ref_dt, "reference_name": ref_name,
        "notes": notes,
    }).insert(ignore_permissions=True)
    frappe.db.set_value("Investigation Client", client, "service_credit", new_bal, update_modified=False)
    return new_bal


def grant_credit(client, amount, ref_dt=None, ref_name=None, notes=None):
    return _post(client, "Earned", amount, ref_dt, ref_name, notes)


def spend_credit(client, amount, ref_dt=None, ref_name=None, notes=None):
    if get_balance(client) < flt(amount):
        frappe.throw("Credito insufficiente.")
    return _post(client, "Spent", amount, ref_dt, ref_name, notes)


def monthly_earned(client):
    start = get_first_day(today())
    rows = frappe.get_all("Credit Ledger",
                          filters={"client": client, "kind": "Earned", "creation": [">=", start]},
                          fields=["amount"])
    return sum(flt(r.amount) for r in rows)
