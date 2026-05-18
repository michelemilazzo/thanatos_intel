import frappe
from frappe.utils.file_manager import save_file

@frappe.whitelist()
def upload_case_document(case_name, document_request, filename=None, content=None):
    if not case_name or not document_request:
        frappe.throw('Missing parameters')

    doc = frappe.get_doc('Visa Document Request', document_request)

    if content and filename:
        file_doc = save_file(filename, content, 'Visa Study Case', case_name, decode=True)
        doc.uploaded_file = file_doc.file_url
        doc.status = 'Uploaded'
        doc.save(ignore_permissions=True)

    return {
        'success': True,
        'document': doc.name,
        'status': doc.status,
        'uploaded_file': doc.uploaded_file
    }
