import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from thanatos_intel.portal_system.doctype.service_catalog.service_catalog import ServiceCatalog


class UsageEvent(Document):
	def before_insert(self):
		self._compute_pricing()

	def before_save(self):
		# Ricalcola se variano campi rilevanti (servizio/quantità/urgent/client)
		self._compute_pricing()

	def _compute_pricing(self):
		# Determina client_type e flag enterprise
		client_type = "Individual"
		is_enterprise = False
		if self.client:
			c = frappe.db.get_value(
				"Investigation Client",
				self.client,
				["client_type", "subscription_status"],
				as_dict=True,
			) or {}
			client_type = c.get("client_type") or "Individual"
			# Enterprise = abbonamento Enterprise attivo (mappato in B2-5 quando Subscription Plan è linkato)
			is_enterprise = (c.get("subscription_status") == "Active")  # raffinato quando plan_level disponibile

		# Sconto in base al tipo cliente
		base_price = ServiceCatalog.get_price(self.service, client_type=client_type, is_enterprise=is_enterprise)
		# Recupera lo sconto applicato per audit
		s = frappe.get_cached_doc("Service Catalog", self.service)
		raw = float(s.price or 0)
		discount = 0.0
		if raw > 0:
			discount = round((1.0 - (base_price / raw)) * 100.0, 2)
		# Multiplier urgent
		if self.is_urgent and (s.urgent_multiplier or 1):
			base_price = round(base_price * float(s.urgent_multiplier or 1.0), 2)
		self.unit_price = base_price
		self.discount_applied = discount
		self.currency = s.currency or "EUR"
		self.total = round(float(self.quantity or 1) * float(self.unit_price or 0), 2)

	def on_payment_confirmed(self, stripe_session_id: str | None = None, stripe_payment_intent: str | None = None):
		# Chiamato dal webhook Stripe nel Blocco 8.
		self.status = "Paid"
		self.paid_at = now_datetime()
		if stripe_session_id:
			self.stripe_session_id = stripe_session_id
		if stripe_payment_intent:
			self.stripe_payment_intent = stripe_payment_intent
		self.save(ignore_permissions=True)
		# ERP bridge: crea Sales Invoice + Payment Entry
		try:
			from thanatos_intel.integrations.erpnext_billing import after_payment
			after_payment(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"UsageEvent.on_payment_confirmed ERP {self.name}")
