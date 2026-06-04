import frappe


def get_context(context):
    context.no_cache = 1
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/ddd"
        raise frappe.Redirect
    name = frappe.form_dict.get("mandate")
    if not name or not frappe.db.exists("Agency Mandate", name):
        frappe.throw("Mandato non trovato")
    m = frappe.get_doc("Agency Mandate", name)
    context.mandate = m
    context.title = f"Firma mandato {m.name}"
    context.signer = (frappe.db.get_value("Applicant Profile", m.applicant,
                                          "full_legal_name") if m.applicant
                      else frappe.session.user)
    return context
