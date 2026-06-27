import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def apply():
    create_custom_fields({
        "Investigation Appointment": [
            {"fieldname": "outcome", "label": "Esito", "fieldtype": "Select",
             "options": "\nPositivo\nNegativo\nRinviato\nCliente assente\nDa ricontattare\nInterlocutorio\nAltro",
             "insert_after": "status"},
        ]
    }, ignore_validate=True)
