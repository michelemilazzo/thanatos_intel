"""Entità di fatturazione di piattaforma (chi emette proforma/fatture).

Le DD dei passaporti (DDD) sono fatturate dall'agenzia configurata in
`Thanatos Billing Settings.ddd_billing_entity` — vale su tutta la piattaforma,
non per singolo caso.
"""
import frappe


def get_ddd_billing_entity_name():
    name = frappe.db.get_single_value("Thanatos Billing Settings", "ddd_billing_entity")
    if not name:
        name = frappe.db.get_single_value("Thanatos Billing Settings", "default_billing_entity")
    if not name:
        name = frappe.db.get_value("Billing Entity", {"is_active": 1}, "name")
    return name


def get_ddd_billing_entity():
    name = get_ddd_billing_entity_name()
    return frappe.get_doc("Billing Entity", name) if name else None


def stamp_ddd_billing_entity(doc, method=None):
    """Hook validate: assegna l'entità di fatturazione DDD se non già impostata."""
    if doc.meta.has_field("billing_entity") and not doc.get("billing_entity"):
        name = get_ddd_billing_entity_name()
        if name:
            doc.billing_entity = name
