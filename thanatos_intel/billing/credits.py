"""Wallet unificato per controparte (Credit Ledger).

- Clienti: credito bonus (Earned dalle segnalazioni) − Spent (interrogazioni/servizi).
  Saldo spendibile su Investigation Client.service_credit (solo portale).
- Agenti / Agenzie / Avvocati / Commercialisti: guadagni maturati tramite Thanatos
  (Commission, accreditati dai Party Payout) − Payout (pagati). Mostra "quanto
  Thanatos ha fatto guadagnare".
"""
import frappe
from frappe.utils import flt, get_first_day, today

PAID_STATUSES = ("Transferred", "Manual Bonifico")


# ---------------- core ----------------

def _post(party_type, party, kind, amount, client=None, balance_after=None,
          ref_dt=None, ref_name=None, notes=None):
    frappe.get_doc({
        "doctype": "Credit Ledger", "party_type": party_type, "party": party,
        "client": client, "kind": kind, "amount": abs(flt(amount)),
        "balance_after": balance_after, "reference_doctype": ref_dt,
        "reference_name": ref_name, "notes": notes,
    }).insert(ignore_permissions=True)


def _ledger_exists(kind, ref_name):
    return bool(ref_name) and frappe.db.exists(
        "Credit Ledger", {"kind": kind, "reference_name": ref_name})


# ---------------- credito CLIENTE (bonus spendibile in portale) ----------------

def get_balance(client):
    return flt(frappe.db.get_value("Investigation Client", client, "service_credit"))


def _client_move(client, kind, amount):
    bal = get_balance(client)
    delta = flt(amount) if kind == "Earned" else -flt(amount)
    new_bal = flt(bal + delta)
    frappe.db.set_value("Investigation Client", client, "service_credit", new_bal, update_modified=False)
    return new_bal


def grant_credit(client, amount, ref_dt=None, ref_name=None, notes=None):
    new_bal = _client_move(client, "Earned", amount)
    _post("Client", client, "Earned", amount, client=client, balance_after=new_bal,
          ref_dt=ref_dt, ref_name=ref_name, notes=notes)
    return new_bal


def is_prepaid(client):
    """True se il cliente paga prepagato (carta); False se ha credito concesso
    (fatturazione mensile a bonifico)."""
    return not bool(frappe.db.get_value("Investigation Client", client, "credit_granted"))


def available_to_spend(client):
    """Quanto il cliente puo spendere ora in servizi automatizzati: il saldo
    prepagato, piu il fido se ha credito concesso."""
    bal = get_balance(client)
    cg = frappe.db.get_value("Investigation Client", client,
                             ["credit_granted", "credit_limit"], as_dict=True) or {}
    return flt(bal + flt(cg.get("credit_limit"))) if cg.get("credit_granted") else flt(bal)


def spend_credit(client, amount, ref_dt=None, ref_name=None, notes=None):
    """Addebita un servizio automatizzato.
    - Prepagato (default): richiede saldo sufficiente (ricaricato con carta).
    - Credito concesso: ammesso il debito fino al fido; l'importo viene
      fatturato mensilmente a bonifico (vedi billing.credit_settlement)."""
    amount = flt(amount)
    bal = get_balance(client)
    cg = frappe.db.get_value("Investigation Client", client,
                             ["credit_granted", "credit_limit"], as_dict=True) or {}
    if cg.get("credit_granted"):
        limit = flt(cg.get("credit_limit"))
        if (bal - amount) < -limit:
            frappe.throw("Fido superato: disponibile %.2f su un fido di %.2f." % (flt(bal + limit), limit))
    elif bal < amount:
        frappe.throw("Credito insufficiente. Ricarica il credito (carta) per usare i servizi automatizzati.")
    new_bal = _client_move(client, "Spent", amount)
    _post("Client", client, "Spent", amount, client=client, balance_after=new_bal,
          ref_dt=ref_dt, ref_name=ref_name, notes=notes)
    return new_bal


def monthly_earned(client):
    start = get_first_day(today())
    rows = frappe.get_all("Credit Ledger",
                          filters={"party": client, "kind": "Earned", "creation": [">=", start]},
                          fields=["amount"])
    return sum(flt(r.amount) for r in rows)


# ---------------- guadagni AGENTI / AGENZIE (via Thanatos) ----------------

def credit_commission(party_type, party, amount, ref_dt=None, ref_name=None, notes=None):
    """Accredita un guadagno maturato tramite Thanatos (idempotente per ref)."""
    if _ledger_exists("Commission", ref_name):
        return
    _post(party_type, party, "Commission", amount, ref_dt=ref_dt, ref_name=ref_name, notes=notes)


def record_payout(party_type, party, amount, ref_dt=None, ref_name=None, notes=None):
    """Registra il pagamento effettuato alla controparte (idempotente per ref)."""
    if _ledger_exists("Payout", ref_name):
        return
    _post(party_type, party, "Payout", amount, ref_dt=ref_dt, ref_name=ref_name, notes=notes)


def party_earnings(party_type, party):
    """Riepilogo guadagni di una controparte."""
    rows = frappe.get_all("Credit Ledger",
                          filters={"party_type": party_type, "party": party},
                          fields=["kind", "amount"])
    commission = sum(flt(r.amount) for r in rows if r.kind == "Commission")
    payout = sum(flt(r.amount) for r in rows if r.kind == "Payout")
    return {"earned": commission, "paid": payout, "pending": flt(commission - payout)}


# ---------------- hook Party Payout ----------------

def on_party_payout_update(doc, method=None):
    """Ogni Party Payout alimenta il wallet della controparte: Commission alla creazione,
    Payout quando risulta pagato."""
    if not doc.get("beneficiary_name"):
        return
    pt = doc.beneficiary_type or "Agency"
    party = doc.beneficiary_name
    credit_commission(pt, party, doc.amount, "Party Payout", doc.name,
                      f"Guadagno da {doc.get('investigation_case') or doc.name}")
    if doc.status in PAID_STATUSES:
        record_payout(pt, party, doc.amount, "Party Payout", doc.name,
                      f"Pagamento {doc.name}")


# ---------------- fee Stripe + guardia pre-pagamento ----------------
STRIPE_FEE_PCT = 3.0
STRIPE_FEE_FIXED = 0.40


def gross_up(net):
    """Lordo da addebitare perché il credito NETTO accreditato sia `net`."""
    return round(flt(net) * (1 + STRIPE_FEE_PCT / 100.0) + STRIPE_FEE_FIXED, 2)


def stripe_fee(net):
    return round(gross_up(net) - flt(net), 2)


def ensure_credit(client, amount, label="servizio"):
    """Blocca (senza addebitare) se il credito disponibile non copre `amount`."""
    amount = flt(amount)
    if not client or amount <= 0:
        return
    avail = available_to_spend(client)
    if avail < amount:
        frappe.throw("Credito insufficiente per «%s»: servono \u20ac %.2f, disponibili \u20ac %.2f. "
                     "Ricarica il wallet servizi." % (label, amount, avail))


def charge(client, amount, label="servizio", ref_dt=None, ref_name=None):
    """Addebita dopo l'esecuzione riuscita."""
    amount = flt(amount)
    if not client or amount <= 0:
        return
    if ref_name and _ledger_exists("Spent", ref_name):
        return
    spend_credit(client, amount, ref_dt=ref_dt, ref_name=ref_name, notes=label)
