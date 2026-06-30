"""Wallet MMOS del tenant (es. Thanatos): credito prepagato per comprare i servizi
MMOS all'ingrosso (costo openapi × markup). Saldo = ultimo balance_after del
Credit Ledger con party_type='Thanatos'. Nessuna migrazione (opzione gia presente).

Cascata: cliente paga la *rivendita* (wallet cliente, billing.credits); Thanatos
paga MMOS il *base* di listino (questo wallet)."""
import frappe
from frappe.utils import flt
from thanatos_intel.billing.credits import _post, gross_up, stripe_fee

TENANT = "Thanatos"


def _console():
    url = frappe.conf.get("mmos_console_url")
    token = frappe.conf.get("mmos_console_token")
    cid = frappe.conf.get("mmos_customer_id")
    return (url.rstrip("/"), token, cid) if (url and token and cid) else None


def mmos_balance(tenant=TENANT):
    c = _console()
    if c:
        try:
            import requests
            url, token, cid = c
            r = requests.get(url + "/api/svc/wallet/balance", params={"customer_id": cid},
                             headers={"Authorization": "Bearer " + token}, timeout=15)
            r.raise_for_status()
            return flt(r.json().get("balance"))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mmos_balance console")
    last = frappe.get_all("Credit Ledger", filters={"party_type": "Thanatos", "party": tenant},
                          fields=["balance_after"], order_by="creation desc", limit=1)
    return flt(last[0].balance_after) if last else 0.0


def mmos_grant(tenant, amount, ref_dt=None, ref_name=None, notes=None):
    bal = round(mmos_balance(tenant) + flt(amount), 2)
    _post("Thanatos", tenant, "Earned", amount, balance_after=bal,
          ref_dt=ref_dt, ref_name=ref_name, notes=notes)
    return bal


def mmos_ensure(amount, tenant=TENANT, label="servizio MMOS"):
    amount = flt(amount)
    if amount <= 0:
        return
    bal = mmos_balance(tenant)
    if bal < amount:
        frappe.throw("Credito MMOS insufficiente per \u00ab%s\u00bb: servono \u20ac %.2f, "
                     "disponibili \u20ac %.2f. Ricarica il wallet MMOS su cloud.onekeyco.com."
                     % (label, amount, bal))


def mmos_charge(amount, tenant=TENANT, ref_dt=None, ref_name=None, notes=None):
    amount = flt(amount)
    if amount <= 0:
        return mmos_balance(tenant)
    c = _console()
    if c:
        import requests
        url, token, cid = c
        try:
            r = requests.post(url + "/api/svc/wallet/spend",
                              json={"customer_id": cid, "amount": amount,
                                    "reason": notes or "Consumo MMOS", "ref": ref_name or ""},
                              headers={"Authorization": "Bearer " + token}, timeout=20)
            r.raise_for_status()
            d = r.json()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "mmos_charge console")
            d = None
        if d is not None:
            if not d.get("ok"):
                frappe.throw("Credito MMOS insufficiente (disponibile € %.2f)." % flt(d.get("balance")))
            return flt(d.get("balance"))
    bal = round(mmos_balance(tenant) - amount, 2)
    _post("Thanatos", tenant, "Spent", amount, balance_after=bal,
          ref_dt=ref_dt, ref_name=ref_name, notes=notes)
    return bal


@frappe.whitelist()
def mmos_status(tenant=TENANT):
    moves = frappe.get_all("Credit Ledger", filters={"party_type": "Thanatos", "party": tenant},
                           fields=["kind", "amount", "balance_after", "notes", "creation"],
                           order_by="creation desc", limit=20)
    return {"tenant": tenant, "balance": mmos_balance(tenant), "moves": moves}


@frappe.whitelist()
def mmos_topup(amount, tenant=TENANT):
    """Ricarica il wallet MMOS via Stripe (gross-up fee 3%+0.40). Netto accreditato = amount."""
    from thanatos_intel.integrations.stripe_bridge import _get_stripe, _success_url, _cancel_url
    net = flt(amount)
    if net <= 0:
        frappe.throw("Importo non valido.")
    gross = gross_up(net)
    fee = stripe_fee(net)
    stripe = _get_stripe()
    meta = {"kind": "mmos_topup", "mmos_tenant": tenant, "net": str(net), "fee": str(fee)}
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "eur",
                                    "product_data": {"name": "Ricarica wallet MMOS (credito \u20ac %.2f)" % net},
                                    "unit_amount": int(round(gross * 100))}, "quantity": 1}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        payment_intent_data={"metadata": meta}, metadata=meta, locale="it",
    )
    return {"url": session.url, "net": net, "fee": fee, "gross": gross}
