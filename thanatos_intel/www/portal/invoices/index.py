import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/invoices"
        raise frappe.Redirect

    from thanatos_intel.workflow.api import _client_for_user, _is_operator
    context.title = "Fatture — Thanatos Intel"
    context.is_op = _is_operator(frappe.session.user)
    cl = _client_for_user(frappe.session.user)
    context.has_client = bool(cl) or context.is_op
    context.invoices = []
    context.usage_events = []

    if not cl:
        return

    # Usage Events pagati / fatturati
    context.usage_events = frappe.get_all(
        "Usage Event",
        filters={"client": cl.name, "status": ["in", ["Paid", "Invoiced"]]},
        fields=["name", "service", "quantity", "unit_price", "total", "currency",
                "status", "paid_at", "creation", "case"],
        order_by="creation desc",
        limit=50,
    )

    # Fatture Stripe da Stripe Subscription (hosted_invoice_url se disponibile)
    try:
        context.invoices = _fetch_stripe_invoices(cl.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "portal invoices stripe")
        context.invoices = []


def _fetch_stripe_invoices(client_name):
    customer_id = frappe.db.get_value("Investigation Client", client_name, "stripe_customer_id")
    if not customer_id:
        return []
    key = frappe.conf.get("stripe_secret_key")
    if not key:
        return []
    try:
        import stripe
        stripe.api_key = key
        stripe.api_version = "2024-12-18.acacia"
        result = stripe.Invoice.list(customer=customer_id, limit=24, status="paid")
        out = []
        for inv in result.auto_paging_iter():
            out.append({
                "id": inv.id,
                "number": inv.number or inv.id,
                "amount": (inv.amount_paid or 0) / 100.0,
                "currency": (inv.currency or "eur").upper(),
                "date": inv.created,
                "hosted_url": inv.hosted_invoice_url or "",
                "pdf_url": inv.invoice_pdf or "",
                "status": inv.status,
            })
            if len(out) >= 24:
                break
        return out
    except Exception:
        return []
