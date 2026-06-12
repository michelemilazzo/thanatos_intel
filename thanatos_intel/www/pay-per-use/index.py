"""Pay-per-use portal page.

MVP: mostra solo i servizi delle categorie:
  - Verifiche Rapide (Crypto wallet, IBAN, IP, dominio, ...)
  - Antifrode (crypto scam, investment scam, phishing, ...)
  - Cyber Intelligence (malware, URL, IOC, ...)

Filtro per `category in ALLOWED_CATEGORIES` + is_active=1.
"""
import frappe

no_cache = 1
sitemap = 1

ALLOWED_CATEGORIES = ["Verifiche Rapide", "Antifrode", "Cyber Intelligence"]


def get_context(context):
    context.body_class = 'ppu-page'
    items = frappe.get_all(
        "Service Catalog",
        filters={
            "is_active": 1,
            "category": ["in", ALLOWED_CATEGORIES],
        },
        fields=["name", "service_code", "service_name", "category",
                "price_min", "price_max", "price", "currency",
                "delivery_hours", "urgent_multiplier",
                "requires_analyst", "description"],
        order_by="category, price_min asc",
    )

    # Group by category for rendering
    by_cat = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)

    context.allowed_categories = [c for c in ALLOWED_CATEGORIES if c in by_cat]
    context.by_cat = by_cat
    context.total_count = len(items)

    # Category metadata
    context.cat_meta = {
        "Verifiche Rapide": {
            "icon": "⚡",
            "subtitle": "Verifiche on-demand, risposta in 24h",
            "color": "#C8A96E",
        },
        "Antifrode": {
            "icon": "🛡️",
            "subtitle": "Analisi di truffe crypto, investment scam, romance scam",
            "color": "#E0C58A",
        },
        "Cyber Intelligence": {
            "icon": "💻",
            "subtitle": "Malware, IOC, phishing, software fake, app sospette",
            "color": "#B8941A",
        },
    }

    context.stripe_publishable_key = frappe.conf.get("stripe_publishable_key") or ""
    context.stripe_configured = bool(
        frappe.conf.get("stripe_secret_key")
        and frappe.conf.get("stripe_publishable_key")
    )
    context.is_logged_in = frappe.session.user != "Guest"
