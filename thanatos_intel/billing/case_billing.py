import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Campi che cuciono il fascicolo investigativo alla fatturazione ERPNext:
#   Investigation Client -> Customer   (identità di fatturazione del cliente)
#   Investigation Case   -> Project    (contenitore di fatturazione del caso)
# La Sales Invoice è già legata al Project (dimensione obbligatoria). Catena:
#   CRM Deal -> Investigation Client/Customer -> Investigation Case/Project -> Sales Invoice
CASE_BILLING_FIELDS = {
    "Investigation Client": [
        {
            "fieldname": "customer",
            "label": "Customer (ERPNext)",
            "fieldtype": "Link",
            "options": "Customer",
            "insert_after": "platform_user",
            "description": "Identità di fatturazione ERPNext del cliente.",
        },
    ],
    "Investigation Case": [
        {
            "fieldname": "project",
            "label": "Project (fatturazione)",
            "fieldtype": "Link",
            "options": "Project",
            "insert_after": "service_type",
            "description": "Project ERPNext usato per fatturare il caso.",
        },
    ],
}


def ensure_case_billing_fields():
    create_custom_fields(CASE_BILLING_FIELDS, ignore_validate=True)


@frappe.whitelist()
def ensure_billing_project(case):
    """Crea (o collega) il Project di fatturazione per un Investigation Case.
    Idempotente: se il caso ha già un project lo restituisce. Il customer è
    derivato dal client del caso (Investigation Client -> customer)."""
    doc = frappe.get_doc("Investigation Case", case)
    if doc.get("project"):
        return doc.project

    customer = None
    if doc.get("client"):
        customer = frappe.db.get_value("Investigation Client", doc.client, "customer")

    project = frappe.get_doc({
        "doctype": "Project",
        "project_name": doc.get("case_title") or doc.name,
        "customer": customer,
    }).insert(ignore_permissions=True)

    doc.db_set("project", project.name)
    frappe.db.commit()
    return project.name
