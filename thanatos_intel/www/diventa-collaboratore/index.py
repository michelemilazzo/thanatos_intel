"""Onboarding collaboratori — /diventa-collaboratore.

Form pubblico → Affiliate Application (status New). Le categorie arrivano
dal doctype Collaborator Category (fonte unica). Dopo approvazione manuale
il collaboratore accede a /collaboratore (portale con referral e commissioni).
"""
import frappe

no_cache = 1

ROLE_BY_CATEGORY = {
    "Investigatore": "Investigator",
    "Agenzia Investigativa": "Agency",
    "Avvocato / Studio Legale": "Lawyer",
    "Commercialista": "Accountant",
    "Consulente Cyber / IT": "Consultant",
    "Agente Immobiliare": "Consultant",
    "Segnalatore Generico": "Consultant",
}


def get_context(context):
    context.body_class = "ppu-page"
    context.categories = frappe.get_all("Collaborator Category", pluck="name", order_by="name")
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    return context
