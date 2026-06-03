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


@frappe.whitelist()
def create_checkout_session(client_name: str, plan_name: str, trial_days: int = 0) -> dict:
    """Crea Stripe Checkout Session per attivare un subscription plan."""
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

    return {"ignored": etype}
