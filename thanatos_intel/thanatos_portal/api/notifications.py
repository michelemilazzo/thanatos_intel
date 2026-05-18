import frappe

@frappe.whitelist()
def notify_document_uploaded(case_name, document_name):
    return {
        'message': f'Document {document_name} uploaded for case {case_name}',
        'status':'queued'
    }
