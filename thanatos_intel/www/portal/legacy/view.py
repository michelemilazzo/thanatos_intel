import frappe

no_cache = 1
no_sitemap = 1


def get_context(context):
    token = frappe.request.args.get("token", "")
    context.token = token
    context.title = "Fascicolo Legacy — Thanatos Intel"
    context.data = None
    context.error = None

    if not token:
        context.error = "Token non presente."
        return

    try:
        from thanatos_intel.legacy_access import get_legacy_view
        data = get_legacy_view(token=token)
        if not data.get("valid"):
            context.error = "Link non valido, revocato o scaduto."
        else:
            context.data = data
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Legacy view context error")
        context.error = "Errore durante il caricamento. Contatta Thanatos Intel."
