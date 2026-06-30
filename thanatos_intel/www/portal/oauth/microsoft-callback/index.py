import frappe

no_cache = 1

def get_context(context):
    code  = frappe.form_dict.get('code')
    state = frappe.form_dict.get('state')
    error = frappe.form_dict.get('error')
    error_description = frappe.form_dict.get('error_description')
    frappe.get_attr('mmos_brand.api.mail_connectors.microsoft_oauth_finish')(
        code=code, state=state, error=error, error_description=error_description
    )
