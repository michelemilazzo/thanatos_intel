"""Piani abbonamento — /pricing.

Fonte unica: Service Catalog SVC-AB-001..004 (prezzi mai hardcoded).
I contenuti feature dei piani sono espositivi; il prezzo viene dal catalogo.
"""
import frappe

no_cache = 1

PLAN_CODES = ["SVC-AB-001", "SVC-AB-002", "SVC-AB-003", "SVC-AB-004"]

PLAN_META = {
    "SVC-AB-001": {
        "label": "Basic", "tagline": "Professionisti e PMI",
        "features": ["Verifiche rapide incluse ogni mese", "Accesso portale clienti",
                     "Verifica blacklist illimitata", "Supporto email"],
        "cta": "Attiva Basic", "featured": False,
    },
    "SVC-AB-002": {
        "label": "Professional", "tagline": "Studi e aziende strutturate",
        "features": ["Tutto di Basic", "Pacchetto antifrode e cyber mensile",
                     "Priorità SLA sulle richieste", "Referente operativo dedicato"],
        "cta": "Attiva Professional", "featured": True,
    },
    "SVC-AB-003": {
        "label": "Legal", "tagline": "Studi legali e contenzioso",
        "features": ["Tutto di Professional", "Perizie e analisi documentali incluse",
                     "Supporto a procedimenti e sequestri", "Sconto convenzione studi legali"],
        "cta": "Richiedi attivazione", "featured": False,
    },
    "SVC-AB-004": {
        "label": "Enterprise", "tagline": "Gruppi, banche, EMI",
        "features": ["Tutto di Legal", "Accesso API e integrazioni",
                     "Monitoraggio continuo aziendale", "Account manager e workshop dedicati"],
        "cta": "Parla con noi", "featured": False,
    },
}


def get_context(context):
    context.body_class = "ppu-page"
    rows = frappe.get_all(
        "Service Catalog",
        filters={"service_code": ["in", PLAN_CODES], "is_active": 1},
        fields=["service_code", "service_name", "price", "currency", "description"],
    )
    by_code = {r.service_code: r for r in rows}
    plans = []
    for code in PLAN_CODES:
        if code not in by_code:
            continue
        r = by_code[code]
        meta = PLAN_META.get(code, {})
        plans.append({
            "code": code,
            "label": meta.get("label") or r.service_name,
            "tagline": meta.get("tagline", ""),
            "price": r.price,
            "currency": r.currency or "EUR",
            "features": meta.get("features", []),
            "cta": meta.get("cta", "Attiva"),
            "featured": meta.get("featured", False),
        })
    context.plans = plans
    return context
