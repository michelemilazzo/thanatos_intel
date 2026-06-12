import frappe
from frappe.utils import flt

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/wallet"
        raise frappe.Redirect
    user = frappe.session.user

    # Cliente: credito bonus
    client = frappe.db.get_value("Investigation Client", {"platform_user": user}, "name")
    context.client = client
    context.credit = flt(frappe.db.get_value("Investigation Client", client, "service_credit")) if client else 0
    if client:
        cinfo = frappe.db.get_value("Investigation Client", client,
                                    ["credit_granted", "payment_method", "credit_limit"], as_dict=True) or {}
        from thanatos_intel.billing.credits import available_to_spend
        context.is_credit = bool(cinfo.get("credit_granted"))
        context.payment_method = cinfo.get("payment_method") or ("Bonifico" if cinfo.get("credit_granted") else "Carta")
        context.credit_limit = flt(cinfo.get("credit_limit"))
        context.available = available_to_spend(client)
    else:
        context.is_credit = False
        context.payment_method = None
        context.credit_limit = 0
        context.available = 0
    context.client_moves = frappe.get_all(
        "Credit Ledger", filters={"party_type": "Client", "party": client} if client else {"name": ""},
        fields=["kind", "amount", "balance_after", "notes", "creation"],
        order_by="creation desc", limit=20) if client else []

    # Agente/Agenzia: guadagni via Thanatos
    inv = frappe.db.get_value("Investigator", {"platform_user": user}, ["name", "full_name"], as_dict=True)
    context.agent = inv
    context.earnings = None
    context.agent_moves = []
    if inv and inv.full_name:
        from thanatos_intel.billing.credits import party_earnings
        context.earnings = party_earnings("Investigator", inv.full_name)
        context.agent_moves = frappe.get_all(
            "Credit Ledger",
            filters={"party": inv.full_name, "kind": ["in", ["Commission", "Payout"]]},
            fields=["kind", "amount", "notes", "reference_name", "creation"],
            order_by="creation desc", limit=20)

    context.title = "Wallet — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context
