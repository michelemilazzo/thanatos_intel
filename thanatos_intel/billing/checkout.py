"""
Checkout self-serve — Thanatos Intel.

Wrapper SICURI sopra integrations.stripe_bridge: il client viene SEMPRE risolto
dalla sessione (non si accetta client_name dal frontend → niente checkout per
conto di altri). Stripe live: chiavi in site_config (stripe_secret_key,
stripe_publishable_key, stripe_webhook_secret).
"""
import frappe
from frappe import _

from thanatos_intel.integrations import stripe_bridge

PLAN_NAMES = {"Basic", "Professional", "Legal", "Enterprise"}


def _my_client():
    if frappe.session.user == "Guest":
        frappe.throw(_("Registrati per completare l'acquisto."), frappe.PermissionError)
    c = frappe.db.get_value("Investigation Client",
                            {"platform_user": frappe.session.user}, "name")
    if not c:
        frappe.throw(_("Il tuo account non è ancora collegato a un profilo cliente. "
                       "Completa l'onboarding o contatta l'assistenza."))
    return c


@frappe.whitelist()
def checkout_plan(plan: str) -> dict:
    """Avvia il checkout abbonamento per un piano (Basic/Professional/Legal/Enterprise)."""
    plan = (plan or "").strip()
    if plan not in PLAN_NAMES:
        frappe.throw(_("Piano non valido."))
    client = _my_client()
    return stripe_bridge.create_checkout_session(client, plan)


@frappe.whitelist()
def checkout_service(service_code: str) -> dict:
    """Acquisto one-time (pay-per-use) di un servizio del catalogo."""
    service_code = (service_code or "").strip()
    if not service_code:
        frappe.throw(_("Servizio non indicato."))
    client = _my_client()
    return stripe_bridge.create_onetime_checkout(client, service_code)


@frappe.whitelist()
def my_billing_status() -> dict:
    """Stato sintetico per il frontend: è loggato? ha un profilo cliente?"""
    if frappe.session.user == "Guest":
        return {"logged_in": False, "has_client": False}
    c = frappe.db.get_value("Investigation Client",
                            {"platform_user": frappe.session.user}, "name")
    return {"logged_in": True, "has_client": bool(c), "client": c}
