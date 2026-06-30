"""Custom field su File: visibilita cliente (interno vs condiviso) + flag pubblicato nel vault."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def apply():
    create_custom_fields({
        "File": [
            {"fieldname": "visibilita_cliente", "label": "Visibilita\u0300 cliente",
             "fieldtype": "Select", "options": "Solo interno\nCondiviso col cliente",
             "default": "Solo interno", "insert_after": "is_private",
             "description": "Solo interno = visibile solo allo staff. Condiviso = pubblicato nel portale del cliente."},
            {"fieldname": "vault_published", "label": "Pubblicato nel vault", "fieldtype": "Check",
             "read_only": 1, "insert_after": "visibilita_cliente"},
        ]
    }, ignore_validate=True)
    frappe.db.commit()
