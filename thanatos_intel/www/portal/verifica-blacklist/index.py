import frappe
from frappe import _

no_cache = 1
NORMALIZE = ("Email", "Domain", "IP", "Wallet", "IBAN")


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/portal/verifica-blacklist"
        raise frappe.Redirect
    context.client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    context.balance = frappe.db.get_value("Investigation Client", context.client, "service_credit") or 0 if context.client else 0
    context.price = frappe.db.get_single_value("Thanatos Billing Settings", "blacklist_query_price") or 5
    try:
        from frappe.sessions import get_csrf_token
        context.csrf_token = get_csrf_token()
    except Exception:
        context.csrf_token = ""
    context.title = "Verifica blacklist — Thanatos"
    context.lang = frappe.local.lang or "it"
    return context


@frappe.whitelist(methods=["POST"])
def query_blacklist(entry_type, entry_value):
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)
    client = frappe.db.get_value("Investigation Client", {"platform_user": frappe.session.user}, "name")
    if not client:
        frappe.throw(_("Il tuo account non è collegato a un profilo cliente."))
    value = (entry_value or "").strip()
    if not value:
        frappe.throw(_("Inserisci un valore."))
    if entry_type in NORMALIZE:
        value = value.lower()

    from thanatos_intel.billing.credits import get_balance, spend_credit
    price = frappe.db.get_single_value("Thanatos Billing Settings", "blacklist_query_price") or 5
    if get_balance(client) < price:
        return {"need_payment": True, "price": price, "balance": get_balance(client)}

    spend_credit(client, price, "Investigation Client", client, f"Interrogazione blacklist {entry_type}: {value}")
    rows = frappe.get_all("Blacklist Entry",
                          filters={"entry_type": entry_type, "entry_value": value, "is_active": 1},
                          fields=["risk_level", "occurrences", "verified", "last_seen", "reason"])
    frappe.db.commit()
    return {"found": bool(rows), "results": rows, "charged": price, "balance": get_balance(client)}
