import frappe


def get_kpis():
    return {
        "open_cases": frappe.db.count("Visa Study Case", {"case_status": ["!=", "Completed"]}),
        "completed_cases": frappe.db.count("Visa Study Case", {"case_status": "Completed"}),
        "pending_documents": frappe.db.count("Visa Document Request", {"status": "Pending"}),
        "uploaded_documents": frappe.db.count("Visa Document Request", {"status": "Uploaded"}),
    }
