import frappe

@frappe.whitelist()
def add_case_message(case_name, message):
    if not case_name or not message:
        frappe.throw('Missing parameters')

    comment = frappe.get_doc({
        'doctype':'Comment',
        'comment_type':'Comment',
        'reference_doctype':'Visa Study Case',
        'reference_name':case_name,
        'content':message
    })
    comment.insert(ignore_permissions=True)

    return {'success':True,'comment':comment.name}
