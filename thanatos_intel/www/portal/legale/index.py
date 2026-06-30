import frappe

no_cache = 1


def get_context(context):
    from thanatos_intel.legal.agreements import all_docs, DISCLAIMER, VERSION
    context.docs = all_docs()
    context.disclaimer = DISCLAIMER
    context.version = VERSION
    context.title = "Documenti legali — Thanatos Intelligence"
    context.lang = frappe.local.lang or "it"
    return context
