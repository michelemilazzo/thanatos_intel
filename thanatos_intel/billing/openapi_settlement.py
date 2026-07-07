"""Settlement pay-per-use openapi (modello: Thanatos PIATTAFORMA, MMOS connected).

Al pagamento del cliente (webhook checkout.session.completed, metadata.kind=openapi_quote):
  1) PAGA SUBITO MMOS via Stripe Connect Transfer = costo openapi + (markup × mmos_markup_pct%).
     Se manca `mmos_stripe_connect_account_id` → payout 'pending' (nessun trasferimento).
  2) Emette la RICEVUTA Thanatos al cliente (ARES Sales Invoice, ERPNext).
  3) Logga sul caso.

Config site_config: mmos_stripe_connect_account_id (acct_...), mmos_markup_pct (% del markup a MMOS, default 0).
"""
import frappe
from frappe.utils import now_datetime, flt


@frappe.whitelist()
def mmos_connect_link():
    """Crea (una volta) il connected account Express di MMOS sulla piattaforma Stripe
    di Thanatos, ne salva l'acct id in site_config e ritorna il link di onboarding."""
    from frappe.installer import update_site_config
    from thanatos_intel.integrations.stripe_bridge import _get_stripe
    s = _get_stripe()
    acct_id = frappe.conf.get("mmos_stripe_connect_account_id")
    if not acct_id:
        acct = s.Account.create(type="express", country="IT",
                                capabilities={"transfers": {"requested": True}},
                                business_profile={"product_description": "Servizi dati e infrastruttura MMOS"},
                                metadata={"thanatos_role": "mmos_platform_parent"})
        acct_id = acct.id
        update_site_config("mmos_stripe_connect_account_id", acct_id)
        update_site_config("mmos_markup_pct", 0)  # MMOS = costo openapi; markup ×3 resta a Thanatos
    base = frappe.utils.get_url()
    link = s.AccountLink.create(account=acct_id,
                                refresh_url=f"{base}/app/thanatos-fonti",
                                return_url=f"{base}/app/thanatos-fonti",
                                type="account_onboarding")
    return {"account": acct_id, "url": link.url}


def _mmos_share(cost, total):
    # MMOS vende all'ingrosso a costo openapi × 3 (prezzo fisso per tutti i rivenditori).
    return round(flt(cost) * flt(frappe.conf.get("openapi_mmos_markup") or 3.0), 2)


@frappe.whitelist()
def settle(session):
    """session = dict Stripe checkout.session (dal webhook handle_event)."""
    if isinstance(session, str):
        import json
        session = json.loads(session)
    meta = session.get("metadata") or {}
    case = meta.get("thanatos_case")
    client = meta.get("thanatos_client") or None
    cost = flt(meta.get("openapi_cost"))
    total = flt(meta.get("openapi_total") or (flt(session.get("amount_total")) / 100.0))
    res = {"case": case, "total": total, "cost": cost}

    # 1) MMOS è già pagato dalla CASCATA WALLET (billing.mmos_wallet.mmos_charge →
    #    cloud.onekeyco.com) al momento del consumo openapi. NIENTE Stripe Connect
    #    Transfer qui: sarebbe un DOPPIO addebito a MMOS. Stripe Connect non serve
    #    in questo modello (MMOS regolato via wallet/credito, non bonifico).
    res["mmos_amount"] = _mmos_share(cost, total)
    res["mmos_payout"] = "via_wallet_cascade"

    # 1b) auto-esecuzione degli ordini DocuEngine allegati al preventivo (documenti PDF
    #     ufficiali): il pagamento è ricevuto → si può ordinare senza altra conferma.
    de_orders = [o for o in (meta.get("de_orders") or "").split(",") if o]
    if de_orders:
        from thanatos_intel.osint.official_documents import de_order_run
        res["de_orders"] = []
        for oid in de_orders:
            try:
                res["de_orders"].append(de_order_run(oid, self_mode=1))
            except Exception as e:
                res["de_orders"].append({"error": str(e)[:160]})
                frappe.log_error(frappe.get_traceback(), "openapi settle de_order")

    # 2) ricevuta Thanatos al cliente (ARES Sales Invoice) — elevata a Administrator
    if client and total > 0:
        prev = frappe.session.user
        try:
            from thanatos_intel.billing.ares_invoice import create_ares_invoice
            customer = frappe.db.get_value("Investigation Client", client, "customer")
            if customer:
                frappe.set_user("Administrator")
                res["invoice"] = create_ares_invoice(case, customer, total,
                                                     description=f"Verifiche dati — caso {case}")
        except Exception as e:
            res["invoice_error"] = str(e)[:200]
            frappe.log_error(frappe.get_traceback(), "openapi settle invoice")
        finally:
            frappe.set_user(prev)

    # 2b) registra il consumo openapi → AI Usage Log → ciclo mensile MMOS→Thanatos su erp.onekeyco.com
    try:
        from frappe.utils import today
        frappe.get_doc({"doctype": "AI Usage Log", "client": client, "model": "openapi:verifiche",
                        "usage_date": today(), "reference": case, "currency": "EUR",
                        "real_cost": cost,        # costo openapi (MMOS→Thanatos, base)
                        "client_cost": total}     # prezzo cliente = costo ×3 (Thanatos→cliente)
                       ).insert(ignore_permissions=True, ignore_mandatory=True)
        res["usage_logged"] = True
    except Exception:
        frappe.log_error(frappe.get_traceback(), "openapi usage log")

    # 3) log caso
    try:
        if case:
            c = frappe.get_doc("Investigation Case", case)
            c.append("case_activities", {"activity_date": now_datetime(), "activity_type": "Report",
                     "description": (f"💳 Pagamento € {total:.2f} ricevuto. Ricevuta Thanatos: "
                                     f"{res.get('invoice', '—')}. MMOS € {res['mmos_amount']:.2f}: "
                                     f"{res.get('mmos_transfer') or res.get('mmos_payout') or res.get('mmos_transfer_error')}")[:500],
                     "operator": "Administrator"})
            c.flags.ignore_mandatory = True
            c.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "openapi settle log")

    # 4) SELF-MODE: il cliente ha pagato → consegna i documenti ufficiali del caso
    #    (PDF) nel suo portale (/portal/vault) + email.
    try:
        if case and client:
            from thanatos_intel.reporting.case_file_delivery import deliver_case_file
            evs = frappe.get_all("Investigation Evidence",
                filters={"investigation_case": case, "source": "openapi documento ufficiale"},
                fields=["attached_file", "evidence_name"])
            n = 0
            for e in evs:
                if e.attached_file:
                    deliver_case_file(case, e.attached_file,
                                      file_name=(e.evidence_name or "Documento")[:140],
                                      self_mode=1)
                    n += 1
            res["delivered"] = n
    except Exception:
        frappe.log_error(frappe.get_traceback(), "openapi settle delivery")
    return res
