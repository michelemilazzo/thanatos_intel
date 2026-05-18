import frappe
from frappe import _

@frappe.whitelist()
def get_case_documents(case_name):
    if not case_name:
        return []

    return frappe.get_all(
        "Visa Document Request",
        filters={"visa_study_case": case_name},
        fields=["name","document_name","status","uploaded_file","required"],
        order_by="document_name asc"
    )
