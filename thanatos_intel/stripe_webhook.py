"""Webhook Stripe -> Revenue Distribution + profit-split (50/50 dopo costi/commissioni).
Endpoint: /api/method/thanatos_intel.stripe_webhook.handle
Config: site_config stripe_webhook_secret (firma). Stripe gira su erp.onekeyco.com.
"""
import json
import frappe


def _stripe_fee(gross):
	# stima fee Stripe EU ~1.5% + 0.25 (sovrascrivibile leggendo balance_transaction)
	return round(float(gross) * 0.015 + 0.25, 2)


def _verify(payload, sig, secret):
	if secret and sig:
		try:
			import stripe
			return stripe.Webhook.construct_event(payload, sig, secret)
		except Exception:
			frappe.throw("Invalid Stripe signature", frappe.AuthenticationError)
	# nessun secret configurato (skeleton/dev): parse senza verifica
	return json.loads(payload)


def _client_by_customer(customer):
	if not customer:
		return None
	return frappe.db.get_value("Investigation Client", {"stripe_customer_id": customer}, "name")


def _on_payment(obj):
	charge_id = obj.get("id")
	if not charge_id or frappe.db.exists("Revenue Distribution", {"stripe_charge_id": charge_id}):
		return  # idempotente
	cents = obj.get("amount_received") or obj.get("amount_paid") or obj.get("amount") or 0
	gross = float(cents) / 100.0
	currency = (obj.get("currency") or "eur").upper()
	customer = obj.get("customer")
	meta = obj.get("metadata") or {}
	client = meta.get("investigation_client") or _client_by_customer(customer)
	if not client:
		frappe.log_error("Stripe charge %s senza Investigation Client (customer=%s)" % (charge_id, customer), "stripe_webhook orphan")
		return
	rd = frappe.get_doc({
		"doctype": "Revenue Distribution",
		"title": "Stripe %s" % charge_id,
		"source_doctype": "Investigation Client",
		"source_name": client,
		"investigation_client": client,
		"stripe_charge_id": charge_id,
		"gross_amount": gross,
		"stripe_fee": _stripe_fee(gross),
		"currency": currency,
		"status": "Draft",
	})
	rd.insert(ignore_permissions=True)
	rd.compute_split()            # net - infra - commissioni -> 50/50
	# rd.queue_payouts()          # abilitare quando Stripe Connect e configurato
	frappe.db.commit()
	return rd.name


@frappe.whitelist(allow_guest=True)
def handle():
	payload = frappe.request.get_data(as_text=True)
	sig = frappe.get_request_header("Stripe-Signature")
	secret = frappe.conf.get("stripe_webhook_secret")
	event = _verify(payload, sig, secret)
	etype = event.get("type")
	handled = ("charge.succeeded", "payment_intent.succeeded", "invoice.paid")
	if etype in handled:
		obj = (event.get("data") or {}).get("object") or {}
		name = _on_payment(obj)
		return {"received": True, "type": etype, "revenue_distribution": name}
	return {"received": True, "type": etype, "ignored": True}
