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
         "insert_after": "services", "description": "Project ERPNext usato per fatturare il caso."},
    ],
    "Quotation": [
        {"fieldname": "investigation_case", "label": "Investigation Case", "fieldtype": "Link",
         "options": "Investigation Case", "insert_after": "order_type",
         "in_standard_filter": 1, "search_index": 1},
    ],
    "Sales Invoice": [
        {"fieldname": "investigation_case", "label": "Investigation Case", "fieldtype": "Link",
         "options": "Investigation Case", "insert_after": "company",
         "in_standard_filter": 1, "search_index": 1},
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

    customer = ic.get("customer") or _pick_existing_customer(ic.client_name)
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


def _pick_existing_customer(customer_name):
    """Se esistono più Customer con lo stesso nome (omonimi/duplicati), preferisci
    quello 'canonico' = con almeno una fattura; evita di linkare a un duplicato vuoto."""
    matches = frappe.get_all("Customer", filters={"customer_name": customer_name}, pluck="name")
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    with_inv = [m for m in matches if frappe.db.count("Sales Invoice", {"customer": m})]
    return (with_inv or matches)[0]


def warn_duplicate_customer(doc, method=None):
    """doc_event Customer.validate: avvisa (NON blocca) se si crea un omonimo —
    due persone con lo stesso nome sono legittime, ma spesso è un duplicato per errore."""
    if not doc.is_new():
        return
    others = frappe.get_all("Customer", filters={"customer_name": doc.customer_name, "name": ["!=", doc.name or ""]}, pluck="name")
    if others:
        frappe.msgprint(
            f"Esiste già un cliente con questo nome ({', '.join(others[:5])}). "
            "Verifica che non sia un duplicato prima di salvare.",
            title="Possibile cliente duplicato", indicator="orange")


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


# Servizi di default per tipologia case (popolati su after_insert se vuoti)
CASE_TYPE_DEFAULT_SERVICES = {
    "Fraud": ["SVC-AF-001", "SVC-AF-002", "SVC-VR-001", "SVC-VR-002"],
    "Due Diligence": ["SVC-CO-001", "SVC-VR-006", "SVC-VR-007"],
    "Asset Recovery": ["SVC-IC-002", "SVC-FI-005", "SVC-SE-004"],
    "Cyber": ["SVC-CY-005", "SVC-VR-008", "SVC-VR-003"],
    "Corporate": ["SVC-CO-002", "SVC-CO-006", "SVC-CO-010"],
    "Family": ["SVC-VR-007", "SVC-IC-001"],
    "Seizure": ["SVC-SE-001", "SVC-SE-004"],
}


def populate_default_services(doc):
    if doc.get("services"):
        return
    for svc in CASE_TYPE_DEFAULT_SERVICES.get(doc.case_type, []):
        if frappe.db.exists("Service Catalog", svc):
            doc.append("services", {"service_catalog": svc})
    if doc.services:
        doc.save(ignore_permissions=True)


def on_case_created(doc, method=None):
    """doc_event after_insert Investigation Case: Project di fatturazione + servizi default."""
    try:
        populate_default_services(doc)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_billing.populate_default_services")
    try:
        ensure_billing_project(doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "case_billing.ensure_billing_project")
