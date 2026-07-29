import frappe

from thanatos_intel.office.launch import editor_url

no_cache = 1


def get_context(context):
    context.no_cache = 1
    file_name = frappe.form_dict.get("file")
    if frappe.session.user in ("Guest", None, ""):
        frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.utils.quote(
            "/office?file=" + (file_name or "")
        )
        raise frappe.Redirect
    context.error = None
    try:
        if not file_name:
            raise frappe.ValidationError("Parametro file mancante")
        info = editor_url(file_name)
        context.src = info["src"]
        context.access_token = info["access_token"]
        context.doc_name = info["file_name"]
        context.can_write = info["can_write"]
    except Exception as e:
        context.error = frappe.utils.escape_html(str(e))
    return context
