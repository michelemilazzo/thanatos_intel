import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/legacy"
        raise frappe.Redirect

    client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    context.has_client = bool(client)
    context.client = client
    context.title = "Legacy Digitale — Thanatos Intel"

    if client:
        context.delegates = frappe.get_all(
            "Client Legacy Delegate",
            filters={"client": client, "status": ["!=", "Revoked"]},
            fields=["name", "delegate_name", "delegate_email", "relationship",
                    "status", "invite_sent_at", "requested_at", "granted_at", "access_expires_at"],
            order_by="creation desc",
        )
    else:
        context.delegates = []

    return context
