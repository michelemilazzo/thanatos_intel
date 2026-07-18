# -*- coding: utf-8 -*-
"""Portale cliente: catalogo servizi completo (Service Catalog) con ordine one-time.

Prima mostrava una lista OSINT hardcoded (self_service). Ora mostra i servizi reali
del catalogo, per categoria, con acquisto via Stripe (billing.checkout.checkout_service).
"""
import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/servizi"
        raise frappe.Redirect

    items = frappe.get_all(
        "Service Catalog", filters={"is_active": 1},
        fields=["service_code", "service_name", "category", "price", "price_min",
                "price_max", "currency", "delivery_hours", "requires_analyst", "description"],
        order_by="category, price asc")
    by_cat = {}
    for it in items:
        by_cat.setdefault(it.category or "Altro", []).append(it)
    context.by_cat = by_cat
    context.categories = list(by_cat.keys())
    context.total_count = len(items)

    context.client = None
    context.wallet = 0
    try:
        from thanatos_intel.workflow.api import _client_for_user
        cl = _client_for_user(frappe.session.user)
        if cl:
            context.client = cl.get("name")
            from thanatos_intel.billing.credits import available_to_spend
            context.wallet = available_to_spend(cl["name"])
    except Exception:
        pass
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Servizi — Thanatos Intel"
    context.lang = frappe.local.lang or "it"
    return context
