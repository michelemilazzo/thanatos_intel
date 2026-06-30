"""Custom Field `soggetto` (Link -> Soggetto) sui doctype-ruolo non nostri (Customer/Employee)."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

TARGETS = {
    "Customer": {"insert_after": "tax_id"},
    "Employee": {"insert_after": "user_id"},
    "Reseller": {"insert_after": "reseller_name"},
    "Corporate Group Member": {"insert_after": "entity_name"},
}


def apply():
    fields = {}
    for dt, opt in TARGETS.items():
        if not frappe.db.exists("DocType", dt):
            continue
        fields[dt] = [{
            "fieldname": "soggetto",
            "label": "Soggetto (persona)",
            "fieldtype": "Link",
            "options": "Soggetto",
            "insert_after": opt["insert_after"],
            "description": "Anagrafica unica della persona: stesso Soggetto per tutti i suoi ruoli.",
        }]
    if fields:
        create_custom_fields(fields, ignore_validate=True)
        frappe.db.commit()
