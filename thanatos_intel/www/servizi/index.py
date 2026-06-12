"""Catalogo servizi completo — /servizi.

Fonte unica dei prezzi: doctype Service Catalog (tutte le categorie attive).
Stessa resa della pagina pay-per-use, estesa all'intero listino, con nav
ad ancore per categoria e CTA verso /registrati (funnel preventivo).
"""
import frappe

no_cache = 1
sitemap = 1

CAT_META = {
    "Verifiche Rapide":        {"icon": "⚡", "subtitle": "Wallet, IBAN, IP, domini, targhe: risposte in ore, non giorni."},
    "Analisi Documenti":       {"icon": "🗎", "subtitle": "Autenticità, manipolazioni, metadati e perizie documentali."},
    "Antifrode":               {"icon": "🛡", "subtitle": "Crypto scam, investment fraud, phishing e recupero evidenze."},
    "Cyber Intelligence":      {"icon": "🕸", "subtitle": "Malware, infrastrutture ostili, IOC, dark web monitoring."},
    "Corporate Intelligence":  {"icon": "🏛", "subtitle": "Due diligence societaria, asset tracing, background check."},
    "Financial Intelligence":  {"icon": "₿",  "subtitle": "Flussi finanziari, AML, attribuzione wallet, fondi esteri."},
    "Investigazioni Complete": {"icon": "🔍", "subtitle": "Mandati investigativi a ciclo completo con analista dedicato."},
    "Sequestri e Confische":   {"icon": "⚖", "subtitle": "Supporto tecnico a sequestri, confische e procedimenti."},
    "Enterprise & API":        {"icon": "⚙", "subtitle": "Integrazioni API, programmi enterprise, formazione e workshop."},
    "Abbonamenti e Academy":   {"icon": "🎓", "subtitle": "Piani ricorrenti e formazione investigativa certificata."},
}

# ordine espositivo: dal self-serve al complesso
CAT_ORDER = [
    "Verifiche Rapide", "Analisi Documenti", "Antifrode", "Cyber Intelligence",
    "Corporate Intelligence", "Financial Intelligence", "Investigazioni Complete",
    "Sequestri e Confische", "Enterprise & API", "Abbonamenti e Academy",
]


def get_context(context):
    context.body_class = "ppu-page"
    items = frappe.get_all(
        "Service Catalog",
        filters={"is_active": 1},
        fields=["name", "service_code", "service_name", "category",
                "price_min", "price_max", "price", "currency",
                "delivery_hours", "requires_analyst", "description"],
        order_by="category, price_min asc, price asc",
    )

    by_cat = {}
    for it in items:
        by_cat.setdefault(it.category, []).append(it)

    ordered = [c for c in CAT_ORDER if c in by_cat]
    ordered += [c for c in sorted(by_cat) if c not in ordered]

    context.categories = ordered
    context.by_cat = by_cat
    context.cat_meta = CAT_META
    context.total_count = len(items)
    context.is_logged_in = frappe.session.user != "Guest"
    return context


def slug(s: str) -> str:
    return s.lower().replace(" & ", "-").replace(" ", "-")
