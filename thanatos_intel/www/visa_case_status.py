import frappe


def get_context(context):
    context.no_cache = 1
    context.title = "Visa Case Status"
    context.case_order = None
    context.visa_case = None
    context.message = None

    order_name = frappe.form_dict.get("order")
    if not order_name:
        context.message = "Missing order reference."
        return context

    if not frappe.db.exists("Visa Case Order", order_name):
        context.message = "Visa case order not found."
        return context

    order = frappe.get_doc("Visa Case Order", order_name)
    if not order.portal_enabled:
        context.message = "Portal access is not enabled yet. Payment confirmation is required."
        return context

    context.case_order = order
    if order.visa_study_case:
        context.visa_case = frappe.get_doc("Visa Study Case", order.visa_study_case)

    return context
