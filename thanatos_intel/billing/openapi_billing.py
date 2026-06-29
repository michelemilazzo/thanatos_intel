"""Preventivo pay-per-use sulle funzioni openapi (a pagamento) + link di pagamento.

Modello: ogni funzione openapi ha un COSTO REALE (verso openapi/MMOS). Si applica il
markup del cliente (Investigation Client.ai_markup, default infra_markup=3.0) → prezzo
cliente. `genera_preventivo` calcola le righe, crea un link di pagamento Stripe (one-off)
e lo invia al cliente (o a chi paga) via email; il link si può inoltrare anche su WhatsApp.

Prezzi base (€, costo reale) override-abili da site_config `openapi_prices`.
Le funzioni FREE (OpenSanctions, cyber, ecc.) hanno costo 0 → non vanno a preventivo.
"""
import json
import frappe
from frappe.utils import now_datetime, flt

# id funzione → (label, costo_reale_eur)
_PRICES = {
    "visura":       ("Visura camerale (IT-advanced)", 0.90),
    "visura_full":  ("Visura completa + bilanci (IT-full)", 2.50),
    "soci":         ("Soci e quote (IT-shareholders)", 0.50),
    "ubo":          ("Titolari effettivi UBO (IT-ubo)", 1.50),
    "soci_ubo":     ("Soci + UBO", 2.00),
    "kyc_paid":     ("KYC approfondito openapi (WW-kyc)", 0.30),
    "negativita":   ("Negatività / protesti", 2.00),
    "patrimoniale": ("Patrimoniale persona", 8.00),
    "report_az":    ("Report azienda completo", 5.00),
    "catasto":      ("Visura catastale", 4.00),
    "ipotecarie":   ("Ispezione ipotecaria", 6.00),
    "iban":         ("Verifica IBAN (titolare)", 0.50),
    "veicolo":      ("Veicolo per targa", 1.20),
    "piva":         ("Risoluzione nome → P.IVA", 0.50),
}


def _price(fid):
    over = frappe.conf.get("openapi_prices") or {}
    if fid in over:
        return _PRICES.get(fid, (fid, 0))[0], flt(over[fid])
    return _PRICES.get(fid, (fid, 0.0))


def _markup(client=None):
    if client:
        mk = frappe.db.get_value("Investigation Client", client, "ai_markup")
        if mk:
            return flt(mk)
    return flt(frappe.conf.get("infra_markup") or 3.0)


@frappe.whitelist()
def listino(client=None):
    """Listino completo: funzione, costo reale, prezzo cliente (col markup)."""
    mk = _markup(client)
    out = []
    for fid, (label, cost) in _PRICES.items():
        lbl, c = _price(fid)
        out.append({"id": fid, "label": lbl, "costo": c, "prezzo": round(c * mk, 2)})
    return {"markup": mk, "voci": out}


def _client_of(case):
    return frappe.db.get_value("Investigation Case", case, "client")


@frappe.whitelist()
def genera_preventivo(case, items, payer_email=None, invia=0):
    """items = JSON [{"id":"visura","target":"BOMAX","label":"..."}] → preventivo + link.
    Applica il markup del cliente del caso, crea un Checkout Stripe one-off, opz. invia email."""
    if isinstance(items, str):
        items = json.loads(items)
    client = _client_of(case)
    mk = _markup(client)
    righe, tot_real, tot_cli = [], 0.0, 0.0
    for it in items:
        lbl, cost = _price(it.get("id"))
        prezzo = round(cost * mk, 2)
        tot_real += cost
        tot_cli += prezzo
        righe.append({"id": it.get("id"), "label": it.get("label") or lbl,
                      "target": it.get("target"), "costo": cost, "prezzo": prezzo})
    tot_cli = round(tot_cli, 2)
    out = {"case": case, "client": client, "markup": mk, "righe": righe,
           "totale_reale": round(tot_real, 2), "totale_cliente": tot_cli, "valuta": "EUR"}

    # link di pagamento Stripe (one-off)
    desc = f"Verifiche dati caso {case} — " + ", ".join(r["label"] for r in righe)[:200]
    try:
        out["link"] = _stripe_link(client, payer_email, tot_cli, desc, case)
    except Exception as e:
        out["link_error"] = str(e)[:200]

    # log a bacheca caso
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                 "description": (f"🧾 Preventivo verifiche: € {tot_cli:.2f} ({len(righe)} voci). "
                                 + ("Link: " + out["link"] if out.get("link") else "Link non generato"))[:500],
                 "operator": frappe.session.user})
        c.flags.ignore_mandatory = True
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "preventivo log")

    if int(invia or 0) and out.get("link"):
        out["inviato"] = _invia_email(case, client, payer_email, out)

    return out


def _stripe_link(client, payer_email, amount_eur, desc, case):
    from thanatos_intel.integrations.stripe_bridge import _get_stripe, get_or_create_stripe_customer, _success_url, _cancel_url
    stripe = _get_stripe()
    kw = dict(
        mode="payment",
        line_items=[{"price_data": {"currency": "eur",
                                    "product_data": {"name": desc[:120] or "Verifiche dati"},
                                    "unit_amount": int(round(amount_eur * 100))}, "quantity": 1}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        metadata={"thanatos_case": case, "kind": "openapi_quote", "thanatos_client": client or ""},
        locale="it",
    )
    if client:
        kw["customer"] = get_or_create_stripe_customer(client)
    elif payer_email:
        kw["customer_email"] = payer_email
    session = stripe.checkout.Session.create(**kw)
    return session.url


def _invia_email(case, client, payer_email, prev):
    to = payer_email
    if not to and client:
        to = frappe.db.get_value("Investigation Client", client, "email")
    if not to:
        return {"ok": False, "error": "nessuna email destinatario"}
    righe = "".join(f"<li>{frappe.utils.escape_html(r['label'])}"
                    + (f" — {frappe.utils.escape_html(r['target'])}" if r.get('target') else "")
                    + f" : € {r['prezzo']:.2f}</li>" for r in prev["righe"])
    msg = (f"<p>Gentile cliente,</p><p>per procedere con le verifiche richieste sul caso "
           f"<b>{frappe.utils.escape_html(case)}</b> trova qui il preventivo:</p><ul>{righe}</ul>"
           f"<p><b>Totale: € {prev['totale_cliente']:.2f}</b></p>"
           f"<p><a href='{prev['link']}' style='background:#C8A96E;color:#0D1B3E;padding:10px 18px;"
           f"border-radius:6px;text-decoration:none;font-weight:600'>Paga ora</a></p>"
           f"<p style='font-size:12px;color:#888'>Le verifiche partono a pagamento ricevuto.</p>")
    try:
        frappe.sendmail(recipients=[to], subject=f"Preventivo verifiche — caso {case}",
                        message=msg)
        return {"ok": True, "to": to}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
