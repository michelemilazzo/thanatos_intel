import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Campi che cuciono il fascicolo investigativo alla fatturazione ERPNext + i dati
# anagrafici/fiscali raccolti in registrazione (Investigation Client) che devono
# fluire automaticamente in Customer + Address per la fatturazione.
#   Investigation Client -> Customer + Address (identità di fatturazione)
#   Investigation Case   -> Project (contenitore di fatturazione)
# Catena: CRM Deal -> Investigation Client/Customer -> Investigation Case/Project -> Sales Invoice
CASE_BILLING_FIELDS = {
    "Investigation Client": [
        {"fieldname": "codice_fiscale", "label": "Codice Fiscale", "fieldtype": "Data",
         "insert_after": "vat_number", "description": "C.F. (persone fisiche IT) — va in Customer.tax_id e in fattura."},
        {"fieldname": "passport_no", "label": "Passaporto n.", "fieldtype": "Data",
         "insert_after": "codice_fiscale"},
        {"fieldname": "billing_address_line1", "label": "Indirizzo (via e civico)", "fieldtype": "Data",
         "insert_after": "address"},
        {"fieldname": "billing_city", "label": "Città", "fieldtype": "Data", "insert_after": "billing_address_line1"},
        {"fieldname": "billing_province", "label": "Provincia", "fieldtype": "Data", "insert_after": "billing_city"},
        {"fieldname": "billing_postal_code", "label": "CAP", "fieldtype": "Data", "insert_after": "billing_province"},
        {"fieldname": "customer", "label": "Customer (ERPNext)", "fieldtype": "Link", "options": "Customer",
         "insert_after": "erp_customer_id", "read_only": 1,
         "description": "Identità di fatturazione ERPNext del cliente (generata dalla registrazione)."},
    ],
    "Investigation Case": [
        {"fieldname": "project", "label": "Project (fatturazione)", "fieldtype": "Link", "options": "Project",
         "insert_after": "service_type", "description": "Project ERPNext usato per fatturare il caso."},
    ],
}


def ensure_case_billing_fields():
    create_custom_fields(CASE_BILLING_FIELDS, ignore_validate=True)


def _company_default_country():
    return frappe.db.get_value("Company", "THANATOS INVESTIGAZIONI S.R.L.", "country") or "Italy"


@frappe.whitelist()
def sync_client_to_billing(client):
    """Dai dati raccolti in registrazione (Investigation Client) crea/aggiorna
    Customer (+ tax_id) e l'Address di fatturazione. Idempotente. Ritorna il customer."""
    ic = frappe.get_doc("Investigation Client", client)
    ctype = "Company" if ic.get("client_type") in ("Company", "Law Firm", "Accounting Firm") else "Individual"
    tax_id = ic.get("codice_fiscale") or ic.get("vat_number")

    customer = ic.get("customer") or frappe.db.get_value("Customer", {"customer_name": ic.client_name})
    if customer:
        if tax_id and frappe.db.get_value("Customer", customer, "tax_id") != tax_id:
            frappe.db.set_value("Customer", customer, "tax_id", tax_id)
    else:
        customer = frappe.get_doc({
            "doctype": "Customer", "customer_name": ic.client_name,
            "customer_type": ctype, "tax_id": tax_id,
        }).insert(ignore_permissions=True).name

    # Address di fatturazione (se ci sono dati strutturati e non già presente)
    if ic.get("billing_address_line1"):
        has_addr = frappe.get_all("Address", filters=[
            ["Dynamic Link", "link_doctype", "=", "Customer"],
            ["Dynamic Link", "link_name", "=", customer],
        ], limit=1)
        if not has_addr:
            frappe.get_doc({
                "doctype": "Address", "address_title": ic.client_name, "address_type": "Billing",
                "address_line1": ic.billing_address_line1, "city": ic.get("billing_city"),
                "state": ic.get("billing_province"), "pincode": ic.get("billing_postal_code"),
                "country": frappe.db.get_value("Country", ic.get("country")) or ic.get("country") or _company_default_country(),
                "is_primary_address": 1, "email_id": ic.get("email"), "phone": ic.get("phone"),
                "links": [{"link_doctype": "Customer", "link_name": customer}],
            }).insert(ignore_permissions=True)

    if ic.get("customer") != customer:
        ic.db_set("customer", customer)
    frappe.db.commit()
    return customer


def on_client_update(doc, method=None):
    """doc_event: alla registrazione/aggiornamento del cliente, se ci sono i dati
    di fatturazione, sincronizza Customer+Address. Non blocca il salvataggio."""
    if not (doc.get("codice_fiscale") or doc.get("vat_number") or doc.get("billing_address_line1")):
        return
    try:
        sync_client_to_billing(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_billing.on_client_update")


@frappe.whitelist()
def ensure_billing_project(case):
    """Crea (o collega) il Project di fatturazione per un Investigation Case.
    Idempotente. Il customer è derivato dal client del caso."""
    doc = frappe.get_doc("Investigation Case", case)
    if doc.get("project"):
        return doc.project
    customer = None
    if doc.get("client"):
        customer = frappe.db.get_value("Investigation Client", doc.client, "customer") \
            or sync_client_to_billing(doc.client)
    company = (frappe.defaults.get_user_default("Company")
               or frappe.defaults.get_global_default("company")
               or frappe.db.get_value("Company", {}, "name"))
    project = frappe.get_doc({
        "doctype": "Project", "project_name": doc.get("case_title") or doc.name,
        "customer": customer, "company": company,
    }).insert(ignore_permissions=True)
    doc.db_set("project", project.name)
    frappe.db.commit()
    return project.name
