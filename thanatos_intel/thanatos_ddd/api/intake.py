"""Intake API: crea Applicant + Diplomatic DD Case + checklist documenti."""
import frappe
from frappe.utils import now_datetime

DEFAULT_DOCS = [
    "Passport", "National ID", "Proof of Address", "Criminal Record",
    "Source of Funds", "Source of Wealth",
]


@frappe.whitelist(allow_guest=False)
def create_case(full_legal_name: str, dob: str, nationality: str,
                country: str, request_type: str,
                institutional_purpose: str = "", email: str = "",
                phone: str = ""):
    if not frappe.db.exists("Country Framework", country):
        frappe.throw(f"Country {country} non configurato")
    app = frappe.get_doc({
        "doctype": "Applicant Profile",
        "full_legal_name": full_legal_name,
        "dob": dob,
        "nationality": nationality,
        "email": email,
        "phone": phone,
    })
    app.insert(ignore_permissions=True)

    case = frappe.get_doc({
        "doctype": "Diplomatic DD Case",
        "applicant": app.name,
        "country": country,
        "request_type": request_type,
        "institutional_purpose": institutional_purpose,
        "workflow_state": "Questionnaire Pending",
    })
    case.insert(ignore_permissions=True)

    for dt in DEFAULT_DOCS:
        frappe.get_doc({
            "doctype": "Required Document",
            "ddd_case": case.name,
            "document_type": dt,
            "status": "Required",
        }).insert(ignore_permissions=True)

    # Pathway Bulgaria automatica se country=Bulgaria
    if country == "Bulgaria":
        frappe.get_doc({
            "doctype": "Bulgaria Diplomatic Pathway",
            "ddd_case": case.name,
        }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"applicant": app.name, "case": case.name,
            "next_step": "/portal/ddd/case/" + case.name}


@frappe.whitelist()
def attach_document(ddd_case: str, document_type: str, file_url: str):
    rd = frappe.get_all("Required Document",
        filters={"ddd_case": ddd_case, "document_type": document_type},
        pluck="name", limit=1)
    if not rd:
        frappe.throw(f"Required Document {document_type} non trovato per {ddd_case}")
    doc = frappe.get_doc("Required Document", rd[0])
    doc.attached_file = file_url
    doc.status = "Uploaded"
    doc.save(ignore_permissions=True)
    # Se è un passaporto, lancia il Passport Analyzer
    if document_type in ("Passport", "Diplomatic Passport", "Service Passport"):
        try:
            from thanatos_intel.thanatos_documents.passport.analyzer import analyze_file
            res = analyze_file(file_url, investigation_case=None)
            doc.passport_analysis = res.get("name")
            doc.status = "Verified" if res.get("mrz_valid") else "Uploaded"
            doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(str(e), "DddAttach passport analyze")
    frappe.db.commit()
    return {"required_document": doc.name, "status": doc.status,
            "passport_analysis": doc.passport_analysis}
