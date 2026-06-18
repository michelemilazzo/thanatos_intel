"""
Stripe billing integration for Thanatos Intel.

Configurazione richiesta in site_config.json:
- stripe_secret_key       : sk_live_... o sk_test_...
- stripe_webhook_secret   : whsec_... (per validazione firma webhook)
- stripe_publishable_key  : pk_live_... o pk_test_... (per frontend checkout)

Tutti i piani vengono creati on-demand al primo checkout: si cerca un Stripe Product/Price
matchando il nome del Investigation Subscription Plan; se non esiste lo crea con prezzo in EUR.
"""
import json
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime

# servizi ricorrenti mensili del Service Catalog acquistabili self-service (add-on)
ADDON_SERVICE_CODES = ["SVC-AB-005", "SVC-AB-006", "SVC-AB-007"]


def _get_stripe():
    key = frappe.conf.get("stripe_secret_key")
    if not key:
        frappe.throw(_("Stripe non configurato: imposta stripe_secret_key in site_config.json"))
    try:
        import stripe
    except ImportError:
        frappe.throw(_("Modulo stripe non installato (pip install stripe)"))
    stripe.api_key = key
    stripe.api_version = "2024-12-18.acacia"
    return stripe


def _success_url():
    base = frappe.utils.get_url()
    return f"{base}/portal/billing/success?session_id={{CHECKOUT_SESSION_ID}}"


def _cancel_url():
    return f"{frappe.utils.get_url()}/portal/billing"


@frappe.whitelist()
def get_or_create_stripe_customer(client_name: str) -> str:
    """Restituisce stripe_customer_id (lo crea se manca)."""
    stripe = _get_stripe()
    client = frappe.get_doc("Investigation Client", client_name)
    if getattr(client, "stripe_customer_id", None):
        return client.stripe_customer_id

    cust = stripe.Customer.create(
        email=client.email,
        name=client.client_name,
        phone=client.phone or None,
        metadata={
            "thanatos_client": client.name,
            "client_type": client.client_type or "",
            "country": client.country or "",
        },
    )
    if hasattr(client, "stripe_customer_id"):
        client.stripe_customer_id = cust.id
        client.db_update()
    frappe.db.commit()
    return cust.id


def _ensure_stripe_price(plan_name: str) -> str:
    """Crea Product+Price su Stripe se non già mappato. Ritorna price_id."""
    stripe = _get_stripe()
    plan = frappe.get_doc("Investigation Subscription Plan", plan_name)

    if getattr(plan, "stripe_price_id", None):
        return plan.stripe_price_id

    amount_cents = int(round(float(plan.monthly_price or 0) * 100))
    if amount_cents <= 0:
        frappe.throw(_("Piano {0} ha prezzo zero, impossibile creare Price").format(plan_name))

    product = stripe.Product.create(
        name=f"Thanatos {plan.plan_name}",
        description=plan.description or f"Thanatos Intel piano {plan.plan_name}",
        metadata={"thanatos_plan": plan.name},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=amount_cents,
        currency="eur",
        recurring={"interval": "month"},
        metadata={"thanatos_plan": plan.name},
    )
    if hasattr(plan, "stripe_price_id"):
        plan.stripe_price_id = price.id
        plan.db_update()
    if hasattr(plan, "stripe_product_id"):
        plan.stripe_product_id = product.id
        plan.db_update()
    frappe.db.commit()
    return price.id


def _is_credit_client(client_name: str) -> bool:
    return bool(frappe.db.get_value("Investigation Client", client_name, "credit_granted"))


def activate_plan_on_credit(client_name: str, plan_name: str) -> dict:
    """Cliente a credito: attiva il piano senza carta, fatturato a bonifico mensile."""
    frappe.db.set_value("Investigation Client", client_name, {
        "subscription_plan": plan_name,
        "subscription_status": "Active",
        "subscription_started_at": now_datetime(),
    }, update_modified=False)
    frappe.db.commit()
    return {"credit": True, "message": _("Piano {0} attivato — fatturazione a bonifico mensile.").format(plan_name)}


def activate_addon_on_credit(client_name: str, service_code: str) -> dict:
    """Cliente a credito: attiva l'add-on ricorrente, fatturato a bonifico mensile."""
    cur = (frappe.db.get_value("Investigation Client", client_name, "active_addons") or "")
    codes = [c.strip() for c in cur.split(",") if c.strip()]
    if service_code not in codes:
        codes.append(service_code)
    frappe.db.set_value("Investigation Client", client_name, "active_addons", ",".join(codes),
                        update_modified=False)
    frappe.db.commit()
    name = frappe.db.get_value("Service Catalog", {"service_code": service_code}, "service_name") or service_code
    return {"credit": True, "message": _("Add-on {0} attivato — fatturazione a bonifico mensile.").format(name)}


@frappe.whitelist()
def create_checkout_session(client_name: str, plan_name: str, trial_days: int = 0) -> dict:
    """Crea Stripe Checkout Session per attivare un subscription plan.
    Cliente a credito: nessuna carta, attivazione a bonifico mensile."""
    if _is_credit_client(client_name):
        return activate_plan_on_credit(client_name, plan_name)
    stripe = _get_stripe()
    customer_id = get_or_create_stripe_customer(client_name)
    price_id = _ensure_stripe_price(plan_name)

    sub_data = {}
    if trial_days and int(trial_days) > 0:
        sub_data["trial_period_days"] = int(trial_days)
    sub_data["metadata"] = {"thanatos_client": client_name, "thanatos_plan": plan_name}

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=_success_url(),
        cancel_url=_cancel_url(),
        subscription_data=sub_data,
        allow_promotion_codes=True,
        billing_address_collection="required",
        metadata={"thanatos_client": client_name, "thanatos_plan": plan_name},
        locale="it",
    )
    return {"id": session.id, "url": session.url}


def _ensure_catalog_recurring_price(service_code: str) -> str:
    """Price ricorrente mensile per un servizio del Service Catalog.
    Usa la lookup_key di Stripe come registro (nessuna cache locale): se il prezzo
    e cambiato crea un nuovo Price e gli trasferisce la lookup_key."""
    stripe = _get_stripe()
    cat = frappe.db.get_value("Service Catalog", {"service_code": service_code, "is_active": 1},
                              ["service_name", "price", "currency"], as_dict=True)
    if not cat:
        frappe.throw(_("Servizio {0} non trovato o non attivo").format(service_code))
    amount_cents = int(round(float(cat.price or 0) * 100))
    if amount_cents <= 0:
        frappe.throw(_("Servizio {0} senza prezzo").format(service_code))

    lookup = f"thanatos_{service_code}_m"
    existing = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1)
    if existing.data and existing.data[0].unit_amount == amount_cents:
        return existing.data[0].id

    product = stripe.Product.create(
        name=f"Thanatos {cat.service_name}",
        metadata={"thanatos_service": service_code},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=amount_cents,
        currency=(cat.currency or "EUR").lower(),
        recurring={"interval": "month"},
        lookup_key=lookup,
        transfer_lookup_key=True,
        metadata={"thanatos_service": service_code},
    )
    return price.id


@frappe.whitelist()
def create_recurring_checkout(client_name: str, service_code: str) -> dict:
    """Checkout subscription per un servizio ricorrente del Service Catalog (add-on
    mensile: monitoraggio, alert di settore, newsletter premium)."""
    if service_code not in ADDON_SERVICE_CODES:
        frappe.throw(_("Servizio non acquistabile in self-service."))
    if _is_credit_client(client_name):
        return activate_addon_on_credit(client_name, service_code)
    stripe = _get_stripe()
    customer_id = get_or_create_stripe_customer(client_name)
    price_id = _ensure_catalog_recurring_price(service_code)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=_success_url(),
        cancel_url=_cancel_url(),
        subscription_data={"metadata": {"thanatos_client": client_name,
                                        "thanatos_service": service_code}},
        allow_promotion_codes=True,
        billing_address_collection="required",
        metadata={"thanatos_client": client_name, "thanatos_service": service_code},
        locale="it",
    )
    return {"id": session.id, "url": session.url}


def _catalog_price(service_code, client_name):
    cat = frappe.db.get_value("Service Catalog", {"service_code": service_code, "is_active": 1},
                              ["service_name", "price", "currency"], as_dict=True)
    if not cat:
        frappe.throw(_("Servizio non disponibile."))
    ctype = frappe.db.get_value("Investigation Client", client_name, "client_type") or "Individual"
    try:
        from thanatos_intel.portal_system.doctype.service_catalog.service_catalog import ServiceCatalog
        price = float(ServiceCatalog.get_price(service_code, ctype))
    except Exception:
        price = float(cat.price or 0)
    return cat, price


@frappe.whitelist()
def create_onetime_checkout(client_name: str, service_code: str) -> dict:
    """Acquisto self-serve di un singolo servizio del catalogo (pay-per-use).
    Prepagato: Stripe Checkout one-time (carta). Credito concesso: a bonifico mensile."""
    cat, price = _catalog_price(service_code, client_name)
    if price <= 0:
        frappe.throw(_("Servizio senza prezzo acquistabile online."))

    ue = frappe.get_doc({"doctype": "Usage Event", "client": client_name, "service": service_code,
                         "status": "Pending", "quantity": 1, "unit_price": price, "total": price,
                         "currency": cat.currency or "EUR"})
    ue.insert(ignore_permissions=True)

    if _is_credit_client(client_name):
        from thanatos_intel.billing.credits import spend_credit
        spend_credit(client_name, price, "Usage Event", ue.name, "Acquisto servizio %s" % service_code)
        ue.db_set("status", "Invoiced", commit=True)
        return {"credit": True, "message": _("Servizio {0} attivato — fatturato a bonifico mensile.").format(cat.service_name)}

    stripe = _get_stripe()
    customer_id = get_or_create_stripe_customer(client_name)
    cents = int(round(price * 100))
    session = stripe.checkout.Session.create(
        mode="payment", customer=customer_id,
        line_items=[{"price_data": {"currency": (cat.currency or "eur").lower(), "unit_amount": cents,
                     "product_data": {"name": "Thanatos · %s" % cat.service_name}}, "quantity": 1}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        payment_intent_data={"metadata": {"thanatos_usage_event": ue.name, "thanatos_client": client_name}},
        metadata={"thanatos_usage_event": ue.name, "thanatos_client": client_name, "thanatos_service": service_code},
        billing_address_collection="required", locale="it",
    )
    ue.db_set("stripe_session_id", session.id, commit=True)
    return {"id": session.id, "url": session.url}


@frappe.whitelist()
def create_case_step_checkout(case_name, seq=None):
    """Pagamento dello step corrente (o `seq`) di una pratica: prezzo preso dallo
    step del workflow (campo price). Prepagato via Stripe Checkout one-time; per i
    clienti a credito si addebita a bonifico mensile e si avanza subito."""
    from thanatos_intel.permissions import is_full_access, visible_case_names
    if not is_full_access(frappe.session.user) and case_name not in (visible_case_names(frappe.session.user) or []):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    case = frappe.get_doc("Investigation Case", case_name)
    step = None
    for st in sorted(case.get("case_steps") or [], key=lambda x: x.seq):
        if (st.action_type or "") == "pay" and st.status in ("Awaiting Client", "In Progress", "Pending"):
            if seq is None or st.seq == int(seq):
                step = st
                break
    if not step:
        frappe.throw(_("Nessuno step di pagamento da saldare su questa pratica."))

    amount = float(step.get("price") or 0)
    if amount <= 0 and step.get("service_code"):
        cat, amount = _catalog_price(step.service_code, case.client)
    if amount <= 0:
        frappe.throw(_("Step di pagamento senza prezzo configurato."))

    label = "Thanatos · %s (%s)" % (step.step_label, case.name)
    ue = frappe.get_doc({"doctype": "Usage Event", "client": case.client, "case": case.name,
                         "service": step.get("service_code") or None, "status": "Pending",
                         "quantity": 1, "unit_price": amount, "total": amount, "currency": "EUR"})
    ue.insert(ignore_permissions=True)

    if case.client and _is_credit_client(case.client):
        from thanatos_intel.billing.credits import spend_credit
        spend_credit(case.client, amount, "Usage Event", ue.name, label)
        ue.db_set("status", "Invoiced", commit=True)
        from thanatos_intel.workflow import engagement
        engagement.on_step_paid(case.name, seq=step.seq, payment_ref="credit:%s" % ue.name)
        return {"credit": True, "message": _("Step «{0}» addebitato a bonifico mensile.").format(step.step_label)}

    stripe = _get_stripe()
    customer_id = get_or_create_stripe_customer(case.client)
    cents = int(round(amount * 100))
    session = stripe.checkout.Session.create(
        mode="payment", customer=customer_id,
        line_items=[{"price_data": {"currency": "eur", "unit_amount": cents,
                     "product_data": {"name": label}}, "quantity": 1}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        payment_intent_data={"metadata": {"thanatos_usage_event": ue.name, "thanatos_case": case.name}},
        metadata={"thanatos_usage_event": ue.name, "thanatos_case": case.name,
                  "thanatos_step_seq": str(step.seq)},
        billing_address_collection="required", locale="it",
    )
    ue.db_set("stripe_session_id", session.id, commit=True)
    return {"id": session.id, "url": session.url}


@frappe.whitelist()
def create_token_verification_checkout(case_name, keys):
    """Pagamento della verifica dei token selezionati (N token x prezzo unitario del
    blueprint). Salva la selezione sul caso e, al pagamento, esegue la verifica."""
    import json as _json
    from thanatos_intel.permissions import is_full_access, visible_case_names
    if not is_full_access(frappe.session.user) and case_name not in (visible_case_names(frappe.session.user) or []):
        frappe.throw(_("Accesso negato."), frappe.PermissionError)
    if isinstance(keys, str):
        keys = _json.loads(keys)
    keys = set(keys or [])
    if not keys:
        frappe.throw(_("Nessun token selezionato."))

    from thanatos_intel.osint import token_discovery as td
    case = frappe.get_doc("Investigation Case", case_name)
    avail = td.discover_case_tokens(case_name)["tokens"]
    selected = [t for t in avail if t["key"] in keys]
    if not selected:
        frappe.throw(_("I token selezionati non sono più disponibili."))

    unit = float(frappe.db.get_value("Service Blueprint", case.get("blueprint"), "token_unit_price") or 0) \
        if case.get("blueprint") else 0
    amount = unit * len(selected)
    if amount <= 0:
        frappe.throw(_("Prezzo per token non configurato."))

    case.db_set("token_selection_json", _json.dumps(selected), update_modified=False)
    ue = frappe.get_doc({"doctype": "Usage Event", "client": case.client, "case": case.name,
                         "status": "Pending", "quantity": len(selected), "unit_price": unit,
                         "total": amount, "currency": "EUR"})
    ue.insert(ignore_permissions=True)

    if case.client and _is_credit_client(case.client):
        from thanatos_intel.billing.credits import spend_credit
        spend_credit(case.client, amount, "Usage Event", ue.name, "Verifica %d token (%s)" % (len(selected), case.name))
        ue.db_set("status", "Invoiced", commit=True)
        td.verify_tokens(case.name)
        return {"credit": True, "message": _("Verifica di {0} token addebitata a bonifico mensile.").format(len(selected))}

    stripe = _get_stripe()
    customer_id = get_or_create_stripe_customer(case.client)
    cents = int(round(amount * 100))
    session = stripe.checkout.Session.create(
        mode="payment", customer=customer_id,
        line_items=[{"price_data": {"currency": "eur", "unit_amount": int(round(unit * 100)),
                     "product_data": {"name": "Thanatos · Verifica token (%s)" % case.name}},
                     "quantity": len(selected)}],
        success_url=_success_url(), cancel_url=_cancel_url(),
        payment_intent_data={"metadata": {"thanatos_usage_event": ue.name, "thanatos_case": case.name}},
        metadata={"thanatos_usage_event": ue.name, "thanatos_case": case.name, "thanatos_token_verify": "1"},
        billing_address_collection="required", locale="it",
    )
    ue.db_set("stripe_session_id", session.id, commit=True)
    return {"id": session.id, "url": session.url}


def _fulfil_onetime(ue_name, session):
    """Webhook: pagamento one-time completato → Usage Event Paid + Sales Invoice."""
    if not frappe.db.exists("Usage Event", ue_name):
        return {"ok": True, "skipped": "no_usage_event"}
    ue = frappe.get_doc("Usage Event", ue_name)
    if ue.status == "Paid":
        return {"ok": True, "already": True}
    pi = session.get("payment_intent") if isinstance(session, dict) else getattr(session, "payment_intent", None)
    ue.db_set("status", "Paid", commit=False)
    ue.db_set("paid_at", now_datetime(), commit=False)
    if pi:
        ue.db_set("stripe_payment_intent", pi, commit=False)
    frappe.db.commit()
    try:
        from thanatos_intel.billing.internal_invoicing import invoice_pay_per_use_purchase
        invoice_pay_per_use_purchase(ue.client, ue.service, stripe_payment_intent=pi, amount=ue.total)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "onetime invoice")
    if ue.get("case"):
        meta = (session.get("metadata") or {}) if isinstance(session, dict) else (getattr(session, "metadata", {}) or {})
        try:
            if meta.get("thanatos_token_verify"):
                from thanatos_intel.osint import token_discovery as td
                td.verify_tokens(ue.case)
            else:
                from thanatos_intel.workflow import engagement
                engagement.on_step_paid(ue.case, seq=meta.get("thanatos_step_seq"), payment_ref=pi)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "case fulfilment")
    return {"ok": True, "usage_event": ue_name, "status": "Paid"}


@frappe.whitelist()
def create_invoice_for_usage(usage_event_name: str) -> dict:
    """Per pay-per-use: crea un Invoice Item one-shot al cliente Stripe."""
    stripe = _get_stripe()
    ue = frappe.get_doc("Usage Event", usage_event_name)
    if not ue.client:
        frappe.throw(_("Usage Event senza client"))

    customer_id = get_or_create_stripe_customer(ue.client)
    amount_cents = int(round(float(ue.total or 0) * 100))
    if amount_cents <= 0:
        return {"skipped": True, "reason": "amount_zero"}

    stripe.InvoiceItem.create(
        customer=customer_id,
        amount=amount_cents,
        currency="eur",
        description=f"{ue.service} · {ue.quantity}× ({ue.name})",
        metadata={"usage_event": ue.name, "service": ue.service},
    )
    invoice = stripe.Invoice.create(
        customer=customer_id,
        collection_method="charge_automatically",
        auto_advance=True,
        metadata={"usage_event": ue.name},
    )
    invoice = stripe.Invoice.finalize_invoice(invoice.id)
    return {"invoice_id": invoice.id, "hosted_url": invoice.hosted_invoice_url,
            "status": invoice.status}


@frappe.whitelist()
def cancel_subscription(stripe_subscription_id: str, at_period_end: bool = True) -> dict:
    stripe = _get_stripe()
    if at_period_end:
        sub = stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)
    else:
        sub = stripe.Subscription.delete(stripe_subscription_id)
    _upsert_subscription_record(sub)
    return {"status": sub.status, "cancel_at_period_end": getattr(sub, "cancel_at_period_end", False)}


@frappe.whitelist()
def sync_subscription(stripe_subscription_id: str) -> dict:
    """Forza re-sync di una sub da Stripe → DocType Thanatos."""
    stripe = _get_stripe()
    sub = stripe.Subscription.retrieve(stripe_subscription_id)
    return _upsert_subscription_record(sub)


def _upsert_subscription_record(sub) -> dict:
    """Mappa l'oggetto Stripe Subscription nel DocType Stripe Subscription."""
    sid = sub["id"] if isinstance(sub, dict) else sub.id
    md = (sub.get("metadata") if isinstance(sub, dict) else sub.metadata) or {}
    client_name = md.get("thanatos_client")
    plan_name = md.get("thanatos_plan")

    if not client_name:
        cust_id = sub["customer"] if isinstance(sub, dict) else sub.customer
        if cust_id:
            client_name = frappe.db.get_value("Investigation Client",
                                              {"stripe_customer_id": cust_id}, "name")
    if not client_name:
        frappe.log_error(f"Stripe sub {sid} senza thanatos_client", "Stripe upsert")
        return {"skipped": True}

    fields = {
        "stripe_subscription_id": sid,
        "stripe_customer_id": sub.get("customer") if isinstance(sub, dict) else sub.customer,
        "investigation_client": client_name,
        "subscription_plan": plan_name,
        "status": sub.get("status") if isinstance(sub, dict) else sub.status,
        "current_period_start": _ts(sub, "current_period_start"),
        "current_period_end": _ts(sub, "current_period_end"),
        "trial_end": _ts(sub, "trial_end"),
        "canceled_at": _ts(sub, "canceled_at"),
        "raw_payload": json.dumps(sub if isinstance(sub, dict) else sub.to_dict_recursive(),
                                  default=str)[:65000],
    }

    items = (sub.get("items") if isinstance(sub, dict) else sub.items) or {}
    data = items.get("data") if isinstance(items, dict) else getattr(items, "data", []) or []
    if data:
        first = data[0]
        price = (first.get("price") if isinstance(first, dict) else first.price) or {}
        amt = price.get("unit_amount") if isinstance(price, dict) else getattr(price, "unit_amount", 0)
        cur = price.get("currency") if isinstance(price, dict) else getattr(price, "currency", "eur")
        if amt:
            fields["amount"] = float(amt) / 100.0
            fields["currency"] = (cur or "eur").upper()

    if frappe.db.exists("Stripe Subscription", sid):
        doc = frappe.get_doc("Stripe Subscription", sid)
        doc.update(fields)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "Stripe Subscription", **fields})
        doc.insert(ignore_permissions=True)

    try:
        client = frappe.get_doc("Investigation Client", client_name)
        if hasattr(client, "subscription_status"):
            client.subscription_status = _map_status(fields["status"])
        if plan_name and hasattr(client, "subscription_plan"):
            client.subscription_plan = plan_name
        if hasattr(client, "subscription_renews_at") and fields.get("current_period_end"):
            client.subscription_renews_at = fields["current_period_end"]
        client.db_update()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Stripe client sync failed")

    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}


def _ts(sub, field):
    val = sub.get(field) if isinstance(sub, dict) else getattr(sub, field, None)
    if not val:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(val), tz=timezone.utc).replace(tzinfo=None)


def _map_status(stripe_status: str) -> str:
    return {
        "active": "Active",
        "trialing": "Active",
        "past_due": "Past Due",
        "canceled": "Cancelled",
        "unpaid": "Past Due",
        "incomplete": "Pending",
        "incomplete_expired": "Cancelled",
    }.get(stripe_status, "Pending")


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Ritorna l'event dict se firma OK, altrimenti solleva."""
    stripe = _get_stripe()
    secret = frappe.conf.get("stripe_webhook_secret")
    if not secret:
        frappe.throw(_("stripe_webhook_secret non configurato"))
    event = stripe.Webhook.construct_event(payload, sig_header, secret)
    return event


def handle_event(event: dict) -> dict:
    """Dispatcher webhook → side effects."""
    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}

    if etype.startswith("customer.subscription."):
        return _upsert_subscription_record(obj)

    if etype == "checkout.session.completed":
        ue_name = (obj.get("metadata") or {}).get("thanatos_usage_event")
        if ue_name and obj.get("mode") == "payment":
            return _fulfil_onetime(ue_name, obj)
        sub_id = obj.get("subscription")
        if sub_id:
            return sync_subscription(sub_id)
        return {"ok": True, "no_subscription": True}

    if etype == "invoice.paid":
        sub_id = obj.get("subscription")
        if sub_id:
            sync_subscription(sub_id)
        ue_name = (obj.get("metadata") or {}).get("usage_event")
        if ue_name:
            try:
                from thanatos_intel.integrations.erpnext_billing import after_payment
                after_payment(ue_name)
            except Exception:
                frappe.log_error(frappe.get_traceback(), "after_payment failed")
        try:
            from thanatos_intel.billing.revenue_engine import create_distribution_from_stripe_invoice
            inv_id = obj.get("id")
            if inv_id:
                rd_name = create_distribution_from_stripe_invoice(inv_id)
                return {"ok": True, "revenue_distribution": rd_name}
        except Exception:
            frappe.log_error(frappe.get_traceback(), "revenue split failed")
        return {"ok": True}

    if etype == "invoice.payment_failed":
        sub_id = obj.get("subscription")
        if sub_id:
            return sync_subscription(sub_id)

    if etype.startswith("setup_intent."):
        # SetupIntent: cliente sta salvando un metodo di pagamento (no charge).
        # Use case: trial, retainer, SCA pre-auth, abbonamento senza fatturazione immediata.
        intent_id = obj.get("id")
        customer_id = obj.get("customer")
        status = obj.get("status")
        usage = obj.get("usage")  # "off_session" | "on_session"
        pm = obj.get("payment_method")
        meta = obj.get("metadata") or {}
        try:
            frappe.get_doc({
                "doctype": "Diplomatic Audit Log",
                "event_type": f"stripe.{etype}",
                "new_value": status or "",
                "reason": frappe.as_json({
                    "setup_intent_id": intent_id,
                    "stripe_customer_id": customer_id,
                    "payment_method": pm,
                    "usage": usage,
                    "metadata": meta,
                })[:500],
            }).insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "setup_intent audit log failed")
        # Optional: link payment method to Investigation Client if metadata.client_name
        client_name = meta.get("client_name") or meta.get("investigation_client")
        if client_name and pm and frappe.db.exists("Investigation Client", client_name):
            try:
                frappe.db.set_value("Investigation Client", client_name,
                                    "stripe_payment_method", pm)
                frappe.db.commit()
            except Exception:
                pass  # field may not exist yet — non-blocking
        return {"ok": True, "event": etype, "setup_intent_id": intent_id,
                "status": status, "client_linked": client_name}

    return {"ignored": etype}
