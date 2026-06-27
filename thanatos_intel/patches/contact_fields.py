import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def apply():
    create_custom_fields({
        "Contact": [
            {"fieldname": "thanatos_assigned_to", "label": "Assegnato a", "fieldtype": "Link",
             "options": "User", "insert_after": "company_name"},
            {"fieldname": "thanatos_is_shared", "label": "Condiviso (team)", "fieldtype": "Check",
             "insert_after": "thanatos_assigned_to"},
        ]
    }, ignore_validate=True)
