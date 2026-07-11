"""Gate di autorizzazione/fatturazione per gli strumenti AI/OSINT a pagamento
(ricerca web, ricerca approfondita, albo OCF, ...).

Regola (2026-07-11): il super admin +393898309015 usa tutto GRATIS e senza
gate; TUTTI gli altri pagano il servizio (anche per strumenti che a noi
costano zero — il prezzo e' una tariffa di servizio). Riusa il wallet servizi
esistente (billing.credits): prepagato → si esegue, credito insufficiente →
si blocca e si invita a ricaricare il wallet.

Uso tipico dal trigger:
    g = gate_paid_tool("web_search", sender, case)
    if not g["allow"]:
        _reply(..., g["message"]); return
    ... esegui ...
    charge_paid_tool("web_search", g)   # addebita dopo il successo
"""
import frappe
from frappe.utils import flt

# Prezzo cliente per strumento (EUR). Tariffa di servizio (comprende il markup
# ~x3 sul nostro costo; per gli strumenti gratuiti e' comunque una tariffa).
# Tunabile: site_config `paid_tool_prices` {tool: prezzo} sovrascrive.
PAID_TOOL_PRICES = {
    "web_search": 2.0,
    "deep_research": 6.0,
    "albo_ocf": 5.0,
}

_SUPER_ADMIN_NUMBERS = {"393898309015"}


def _digits(x):
    import re
    return re.sub(r"\D", "", x or "")


def _is_super_admin(sender):
    d = _digits(sender)
    return bool(d) and any(d.endswith(n) for n in _SUPER_ADMIN_NUMBERS)


def _price(tool_key):
    override = (frappe.conf.get("paid_tool_prices") or {})
    return flt(override.get(tool_key, PAID_TOOL_PRICES.get(tool_key, 0)))


def _case_client(case):
    if not case:
        return None
    return frappe.db.get_value("Investigation Case", case, "client")


def gate_paid_tool(tool_key, sender, case=None):
    """Ritorna dict {allow, message, client, price, free}. NON addebita:
    l'addebito va fatto DOPO il successo con charge_paid_tool(tool_key, res)."""
    if _is_super_admin(sender):
        return {"allow": True, "free": True, "price": 0, "client": None,
                "message": ""}

    price = _price(tool_key)
    if price <= 0:
        # nessun prezzo configurato: consenti (non blocca il flusso)
        return {"allow": True, "free": True, "price": 0, "client": None,
                "message": ""}

    client = _case_client(case)
    if not client:
        return {"allow": False, "price": price, "client": None,
                "message": ("💳 Questo servizio (€ %.2f) va fatturato a un cliente. "
                            "Collega prima la ricerca a un caso con cliente "
                            "(es. «CASE-AAAA-N»)." % price)}

    from thanatos_intel.billing.credits import available_to_spend
    avail = flt(available_to_spend(client))
    if avail < price:
        return {"allow": False, "price": price, "client": client,
                "message": ("💳 Servono € %.2f per questo servizio, ma il wallet "
                            "del cliente ha € %.2f. Ricarica il wallet servizi "
                            "(portale → Wallet) e ripeti il comando." % (price, avail))}
    return {"allow": True, "free": False, "price": price, "client": client,
            "message": ""}


def charge_paid_tool(tool_key, gate_result, case=None):
    """Addebita il wallet del cliente DOPO l'esecuzione riuscita. No-op per il
    super admin / servizi free."""
    if not gate_result or gate_result.get("free") or not gate_result.get("client"):
        return
    price = flt(gate_result.get("price"))
    if price <= 0:
        return
    try:
        from thanatos_intel.billing.credits import charge
        charge(gate_result["client"], price,
               label="Servizio %s" % tool_key,
               ref_dt="Investigation Case", ref_name=case)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "paid_gate charge")
