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


def _docuengine_voci():
    """Voci listino dai 53 documenti DocuEngine (catalogo cached; id 'de_<documentId>')."""
    try:
        from thanatos_intel.osint.official_documents import docuengine_catalog
        cat = docuengine_catalog()
        return [("de_" + d["id"], ("%s (%s)" % (d["name"], d["category"]), flt(d["costo"])))
                for d in cat.get("documenti") or []]
    except Exception:
        return []


_BOLLO = 16.0


def prezzo_cliente(fid, label, cost, mk):
    """Prezzo cliente con marca da bollo (€16) pass-through: markup solo sul servizio."""
    b = _BOLLO if "marca da bollo" in (label or "").lower() else 0.0
    return round((flt(cost) - b) * mk + b, 2)


def _price(fid):
    over = frappe.conf.get("openapi_prices") or {}
    if fid in over:
        return _PRICES.get(fid, (fid, 0))[0], flt(over[fid])
    if fid and str(fid).startswith("de_"):
        for did, (label, cost) in _docuengine_voci():
            if did == fid:
                return label, cost
        return fid, 0.0
    return _PRICES.get(fid, (fid, 0.0))


def _mmos_markup():
    """Prezzo ingrosso MMOS = costo openapi × 3 (fisso per tutti i rivenditori)."""
    return flt(frappe.conf.get("openapi_mmos_markup") or frappe.conf.get("infra_markup") or 3.0)


def _markup(client=None):
    """Markup TOTALE cliente = MMOS (×3 ingrosso) × resale Thanatos.
    Resale = Investigation Client.ai_markup, altrimenti thanatos_resale_markup (default 1.0 = al prezzo MMOS)."""
    mm = _mmos_markup()
    rs = None
    if client:
        m = frappe.db.get_value("Investigation Client", client, "ai_markup")
        rs = flt(m) if m else None
    if rs is None:
        rs = flt(frappe.conf.get("thanatos_resale_markup") or 1.0)
    return round(mm * rs, 4)


@frappe.whitelist()
def gen_mmos_link():
    from thanatos_intel.billing.openapi_settlement import mmos_connect_link
    return mmos_connect_link()


_EU_COUNTRIES = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic", "Denmark",
    "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy",
    "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal",
    "Romania", "Slovakia", "Slovenia", "Spain", "Sweden",
}


_EU_VAT_RATES = {
    "Italy": 22, "Romania": 19, "Germany": 19, "France": 20, "Spain": 21, "Austria": 20,
    "Belgium": 21, "Bulgaria": 20, "Croatia": 25, "Cyprus": 19, "Czech Republic": 21,
    "Denmark": 25, "Estonia": 22, "Finland": 25.5, "Greece": 24, "Hungary": 27,
    "Ireland": 23, "Latvia": 21, "Lithuania": 21, "Luxembourg": 17, "Malta": 18,
    "Netherlands": 21, "Poland": 23, "Portugal": 23, "Slovakia": 23, "Slovenia": 22,
    "Sweden": 25,
}


def _iva(case=None):
    """Aliquota IVA applicabile (%) e nota di regime: chi fattura (Billing Entity) + cliente.
    Domestico = aliquota nazionale; UE B2B con P.IVA = inversione contabile; UE B2C = OSS
    (aliquota destinazione); extra-UE = non imponibile."""
    be_name = frappe.db.get_value("Investigation Case", case, "billing_entity") if case else None
    if not be_name:
        from thanatos_intel.billing.billing_entity import get_default_billing_entity_name
        be_name = get_default_billing_entity_name()
    be_country = frappe.db.get_value("Billing Entity", be_name, "country") if be_name else None
    client = frappe.db.get_value("Investigation Case", case, "client") if case else None
    cc = frappe.db.get_value("Investigation Client", client, "country") if client else None
    vat = frappe.db.get_value("Investigation Client", client, "vat_number") if client else None
    if not cc:
        cc = be_country  # cliente sconosciuto → assume operazione domestica
    be_eu = be_country in _EU_VAT_RATES
    cl_eu = cc in _EU_VAT_RATES
    if not be_eu:
        return 0.0, "IVA non applicabile (entit\u00e0 extra-UE)"
    if not cl_eu:
        return 0.0, "Operazione non imponibile (cliente extra-UE)"
    if cc == be_country:
        r = _EU_VAT_RATES.get(cc, 22)
        return float(r), "IVA %g%%" % r
    if vat:
        return 0.0, "Inversione contabile art.196 (UE B2B)"
    r = _EU_VAT_RATES.get(cc, 22)
    return float(r), "IVA %g%% (OSS %s)" % (r, cc)


@frappe.whitelist()
def listino(client=None, case=None):
    """Listino: prezzo cliente finale (markup gi\u00e0 incluso) + regime IVA."""
    if case and not client:
        client = frappe.db.get_value("Investigation Case", case, "client")
    mk = _markup(client)
    out = []
    for fid, (label, cost) in list(_PRICES.items()) + _docuengine_voci():
        lbl, c = _price(fid)
        out.append({"id": fid, "label": lbl, "costo": c, "prezzo": prezzo_cliente(fid, lbl, c, mk)})
    iva_rate, iva_note = _iva(case)
    return {"markup": mk, "voci": out, "iva_rate": iva_rate, "iva_note": iva_note}


def _client_of(case):
    return frappe.db.get_value("Investigation Case", case, "client")


def _preventivo_contacts(case):
    """Contatti auto-risolti per ciascun pagatore (cliente / investigatore / Thanatos)."""
    client = _client_of(case)
    cl_email = frappe.db.get_value("Investigation Client", client, "email") if client else None
    cl_phone = frappe.db.get_value("Investigation Client", client, "phone") if client else None
    inv = frappe.db.get_value("Investigation Case", case, "assigned_investigator")
    inv_email = inv_phone = None
    if inv:
        inv_phone = frappe.db.get_value("Investigator", inv, "phone")
        pu = frappe.db.get_value("Investigator", inv, "platform_user")
        if pu:
            inv_email = frappe.db.get_value("User", pu, "email") or pu
    from thanatos_intel.billing.billing_entity import get_default_billing_entity_name
    be = get_default_billing_entity_name()
    thn_email = (frappe.db.get_value("Billing Entity", be, "email") if be else None) or "info@thanatos.agency"

    def _clean_email(e):
        e = (e or "").strip()
        return "" if (not e or e.endswith((".thanatos.agency",)) and ("@lead." in e or "@daidentificare." in e)) else e

    return {
        "cliente": {"email": _clean_email(cl_email), "whatsapp": cl_phone or ""},
        "investigatore": {"email": inv_email or "", "whatsapp": inv_phone or ""},
        "thanatos": {"email": thn_email, "whatsapp": ""},
    }


@frappe.whitelist()
def preventivo_contacts(case):
    return _preventivo_contacts(case)


def _send_wa_text(case, to_number, body):
    """Invio testo WhatsApp al destinatario via numero del caso (Intel Lead collegato)."""
    if not to_number:
        return {"ok": False, "error": "nessun numero WhatsApp"}
    lead = frappe.db.get_value("Intel Lead", {"linked_case": case},
                               ["name", "source_identifier"], as_dict=True)
    if not lead or not lead.source_identifier:
        return {"ok": False, "error": "nessun numero mittente WhatsApp (Intel Lead) sul caso"}
    try:
        from thanatos_intel.ingest.operator_console import _reply
        _reply(lead.source_identifier, to_number, lead.name, body)
        return {"ok": True, "to": to_number}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@frappe.whitelist()
def genera_preventivo(case, items, payer="cliente", channels="email", email=None, whatsapp=None, invia=1, payer_email=None):
    """items = JSON [{"id":"visura","target":"BOMAX","label":"..."}] → preventivo + link.
    Applica il markup del cliente del caso, crea un Checkout Stripe one-off, opz. invia email."""
    if isinstance(items, str):
        items = json.loads(items)
    client = _client_of(case)
    mk = _markup(client)
    righe, tot_real, tot_cli = [], 0.0, 0.0
    for it in items:
        lbl, cost = _price(it.get("id"))
        p = it.get("prezzo")
        prezzo = round(float(p), 2) if p not in (None, "", "null") else prezzo_cliente(it.get("id"), lbl, cost, mk)
        tot_real += cost
        tot_cli += prezzo
        righe.append({"id": it.get("id"), "label": it.get("label") or lbl,
                      "target": it.get("target"), "costo": cost, "prezzo": prezzo})
    tot_cli = round(tot_cli, 2)
    iva_rate, iva_note = _iva(case)
    iva_importo = round(tot_cli * iva_rate / 100.0, 2)
    totale = round(tot_cli + iva_importo, 2)
    contacts = _preventivo_contacts(case)
    payer = (payer or "cliente").lower()
    to_email = (email or payer_email or contacts.get(payer, {}).get("email") or "").strip()
    to_wa = (whatsapp or contacts.get(payer, {}).get("whatsapp") or "").strip()
    out = {"case": case, "client": client, "markup": mk, "righe": righe,
           "totale_reale": round(tot_real, 2), "imponibile": tot_cli,
           "iva_rate": iva_rate, "iva_note": iva_note, "iva_importo": iva_importo,
           "totale_cliente": totale, "valuta": "EUR", "payer": payer,
           "to_email": to_email, "to_whatsapp": to_wa}

    # link di pagamento Stripe (one-off) — non per 'thanatos' (costo interno)
    desc = f"Verifiche dati caso {case} — " + ", ".join(r["label"] for r in righe)[:200]
    if payer == "thanatos":
        out["a_carico"] = "Thanatos"
    else:
        try:
            out["link"] = _stripe_link(
                client if payer == "cliente" else None,
                to_email if payer != "cliente" else None,
                totale, desc, case, round(tot_real, 2))
        except Exception as e:
            out["link_error"] = str(e)[:200]

    # log a bacheca caso
    try:
        c = frappe.get_doc("Investigation Case", case)
        c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                 "description": (f"🧾 Preventivo verifiche: € {totale:.2f} (IVA incl.) ({len(righe)} voci). "
                                 + ("Link: " + out["link"] if out.get("link") else "Link non generato"))[:500],
                 "operator": frappe.session.user})
        c.flags.ignore_mandatory = True
        c.save(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "preventivo log")

    if int(invia or 0) and out.get("link"):
        ch = (channels or "email").lower()
        if ch in ("email", "both") and to_email:
            out["inviato_email"] = _invia_email(case, client, to_email, out)
        if ch in ("whatsapp", "both") and to_wa:
            body = (f"Preventivo verifiche caso {case}: \u20ac {totale:.2f} (IVA incl.). "
                    f"Paga qui: {out['link']}")
            out["inviato_wa"] = _send_wa_text(case, to_wa, body)

    return out


def _stripe_link(client, payer_email, amount_eur, desc, case, real_cost=0):
    from thanatos_intel.integrations.stripe_bridge import _get_stripe, get_or_create_stripe_customer, _success_url, _cancel_url
    stripe = _get_stripe()
    meta = {"thanatos_case": case, "kind": "openapi_quote", "thanatos_client": client or "",
            "openapi_cost": str(real_cost), "openapi_total": str(amount_eur)}
    kw = dict(
        mode="payment",
        line_items=[{"price_data": {"currency": "eur",
                                    "product_data": {"name": desc[:120] or "Verifiche dati"},
                                    "unit_amount": int(round(amount_eur * 100))}, "quantity": 1}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        payment_intent_data={"metadata": meta},
        metadata=meta,
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
           + (f"<p>Imponibile: \u20ac {prev.get('imponibile', prev['totale_cliente']):.2f}<br>"
              f"{prev.get('iva_note','')}: \u20ac {prev.get('iva_importo',0):.2f}</p>" if prev.get('iva_rate') else
              (f"<p style='font-size:12px;color:#888'>{prev.get('iva_note','')}</p>" if prev.get('iva_note') else ""))
           + f"<p><b>Totale: \u20ac {prev['totale_cliente']:.2f}</b></p>"
           f"<p><a href='{prev['link']}' style='background:#C8A96E;color:#0D1B3E;padding:10px 18px;"
           f"border-radius:6px;text-decoration:none;font-weight:600'>Paga ora</a></p>"
           f"<p style='font-size:12px;color:#888'>Le verifiche partono a pagamento ricevuto.</p>")
    try:
        frappe.sendmail(recipients=[to], subject=f"Preventivo verifiche — caso {case}",
                        message=msg)
        return {"ok": True, "to": to}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
