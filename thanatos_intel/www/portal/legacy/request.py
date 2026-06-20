import frappe

no_cache = 1
no_sitemap = 1


def get_context(context):
    token = frappe.request.args.get("token", "")
    context.token = token
    context.title = "Richiesta accesso Legacy — Thanatos Intel"
    context.delegate_info = None
    context.error = None

    if not token:
        context.error = "Link non valido."
        return

    try:
        name = frappe.db.get_value("Client Legacy Delegate", {"invite_token": token}, "name")
        if not name:
            context.error = "Link non valido o scaduto."
            return
        doc = frappe.get_doc("Client Legacy Delegate", name)
        if doc.status == "Revoked":
            context.error = "Questo invito è stato revocato dal cliente."
            return
        client_name = frappe.db.get_value("Investigation Client", doc.client, "client_name") or doc.client
        context.delegate_info = {
            "delegate_name": doc.delegate_name,
            "client_display": client_name,
            "status": doc.status,
            "waiting_hours": doc.waiting_hours,
        }
        context.already_requested = doc.status in ("Requested", "Reviewing", "Granted")
    except Exception:
        context.error = "Errore durante il caricamento. Riprovare."
