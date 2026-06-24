import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Indirizzi cliente in stile banca/EMI: residenza (base) + domicilio/spedizione
# con flag "uguale a residenza". Fatturazione riusa i billing_* esistenti + flag.
ADDR_FIELDS = {
    "Investigation Client": [
        {"fieldname": "addr_section", "label": "Indirizzi", "fieldtype": "Section Break", "insert_after": "codice_fiscale"},
        # Residenza
        {"fieldname": "res_address_line1", "label": "Residenza — Via e civico", "fieldtype": "Data", "insert_after": "addr_section"},
        {"fieldname": "res_city", "label": "Residenza — Citta", "fieldtype": "Data", "insert_after": "res_address_line1"},
        {"fieldname": "res_province", "label": "Residenza — Provincia", "fieldtype": "Data", "insert_after": "res_city"},
        {"fieldname": "res_postal_code", "label": "Residenza — CAP", "fieldtype": "Data", "insert_after": "res_province"},
        {"fieldname": "res_country", "label": "Residenza — Paese", "fieldtype": "Link", "options": "Country", "insert_after": "res_postal_code"},
        # Domicilio
        {"fieldname": "dom_same_as_res", "label": "Domicilio = residenza", "fieldtype": "Check", "default": "1", "insert_after": "res_country"},
        {"fieldname": "dom_address_line1", "label": "Domicilio — Via e civico", "fieldtype": "Data", "insert_after": "dom_same_as_res", "depends_on": "eval:!doc.dom_same_as_res"},
        {"fieldname": "dom_city", "label": "Domicilio — Citta", "fieldtype": "Data", "insert_after": "dom_address_line1", "depends_on": "eval:!doc.dom_same_as_res"},
        {"fieldname": "dom_province", "label": "Domicilio — Provincia", "fieldtype": "Data", "insert_after": "dom_city", "depends_on": "eval:!doc.dom_same_as_res"},
        {"fieldname": "dom_postal_code", "label": "Domicilio — CAP", "fieldtype": "Data", "insert_after": "dom_province", "depends_on": "eval:!doc.dom_same_as_res"},
        {"fieldname": "dom_country", "label": "Domicilio — Paese", "fieldtype": "Link", "options": "Country", "insert_after": "dom_postal_code", "depends_on": "eval:!doc.dom_same_as_res"},
        # Spedizione
        {"fieldname": "ship_same_as_res", "label": "Spedizione = residenza", "fieldtype": "Check", "default": "1", "insert_after": "dom_country"},
        {"fieldname": "ship_address_line1", "label": "Spedizione — Via e civico", "fieldtype": "Data", "insert_after": "ship_same_as_res", "depends_on": "eval:!doc.ship_same_as_res"},
        {"fieldname": "ship_city", "label": "Spedizione — Citta", "fieldtype": "Data", "insert_after": "ship_address_line1", "depends_on": "eval:!doc.ship_same_as_res"},
        {"fieldname": "ship_province", "label": "Spedizione — Provincia", "fieldtype": "Data", "insert_after": "ship_city", "depends_on": "eval:!doc.ship_same_as_res"},
        {"fieldname": "ship_postal_code", "label": "Spedizione — CAP", "fieldtype": "Data", "insert_after": "ship_province", "depends_on": "eval:!doc.ship_same_as_res"},
        {"fieldname": "ship_country", "label": "Spedizione — Paese", "fieldtype": "Link", "options": "Country", "insert_after": "ship_postal_code", "depends_on": "eval:!doc.ship_same_as_res"},
        # Fatturazione = residenza (riusa billing_* esistenti)
        {"fieldname": "bill_same_as_res", "label": "Fatturazione = residenza", "fieldtype": "Check", "default": "1", "insert_after": "billing_postal_code"},
        # Persona con societa collegata (UBO / amministratore)
        {"fieldname": "has_company", "label": "Possiede/rappresenta una societa", "fieldtype": "Check", "default": "0", "insert_after": "bill_same_as_res"},
        {"fieldname": "company_role", "label": "Ruolo nella societa", "fieldtype": "Select", "options": "\nUBO\nAmministratore\nEntrambi", "insert_after": "has_company", "depends_on": "eval:doc.has_company"},
    ]
}


def apply():
    create_custom_fields(ADDR_FIELDS, ignore_validate=True)
