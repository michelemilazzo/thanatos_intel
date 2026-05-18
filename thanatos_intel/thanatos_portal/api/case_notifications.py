import frappe

@frappe.whitelist()
def send_case_update(case_name,status):
    return {
        'case':case_name,
        'status':status,
        'queued':True
    }
