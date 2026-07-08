"""Gate di spesa per l'MCP openapi ufficiale.

Il proxy `openapi_gate_proxy` (davanti all'MCP openapi) chiama qui via HTTP interno,
protetto da token condiviso (site_config `openapi_gate_token`), PRIMA di ogni tool a
pagamento: `check(tool)` verifica il saldo del wallet MMOS (mmos_ensure/mmos_balance) e
blocca se insufficiente; `charge(tool)` addebita al consumo dopo il successo.

Regola (utente 2026-07-08): nessuna chiamata openapi a pagamento parte senza saldo wallet
MMOS sufficiente, altrimenti serve approvazione+pagamento manuale.
"""
import frappe
from frappe.utils import flt

# Costo openapi stimato (€) per tool MCP. Override per-tool via site_config
# `openapi_tool_costs` (dict). Tool non elencati => `openapi_gate_default_cost`.
_TOOL_COST = {
    # gratuiti / locali
    "openapi_server_info": 0.0,
    "check_async_status": 0.0,
    "get_today_exchange_rates": 0.0,
    "geocode": 0.0,
    "reverse_geocode": 0.0,
    "get_docuengine_services": 0.0,
    "get_docuengine_documents": 0.0,
    "get_docuengine_request_status": 0.0,
    "get_italian_company_official_documents_list": 0.0,
    # company
    "get_company_IT_start": 0.30,
    "get_company_IT_search": 0.30,
    "get_company_IT_legal_forms_list": 0.0,
    "get_company_IT_advanced": 1.00,
    "get_company_IT_full": 3.00,
    "get_company_EU_start": 0.50,
    "get_company_EU_advanced": 3.00,
    "get_company_WW_start": 0.50,
    "get_company_WW_advanced": 5.00,
    "get_company_WW_top": 3.00,
    "get_company_FR_search": 0.30,
    # risk
    "post_risk_WW_kyc_full": 1.50,
    "get_risk_IT_creditscore_top": 3.00,
    "check_IT_fiscal_code": 0.20,
    # automotive / documenti / sms
    "check_license_plate": 16.70,
    "get_italian_company_official_document": 4.00,
    "download_italian_company_official_document": 4.00,
    "send_sms": 0.10,
}
_DEFAULT_PAID = 2.0


def _cost(tool):
    over = frappe.conf.get("openapi_tool_costs") or {}
    if tool in over:
        return flt(over[tool])
    if tool in _TOOL_COST:
        return flt(_TOOL_COST[tool])
    return flt(frappe.conf.get("openapi_gate_default_cost") or _DEFAULT_PAID)


def _markup():
    return flt(frappe.conf.get("openapi_mmos_markup") or 3.0)


def _auth(token):
    want = frappe.conf.get("openapi_gate_token")
    if not want or token != want:
        frappe.throw("gate token non valido", frappe.PermissionError)


@frappe.whitelist(allow_guest=True)
def check(tool, token=None, mode=None):
    """Pre-flight: c'e' saldo wallet MMOS per questo tool? Non addebita.

    mode='sandbox' => chiamate openapi gratuite, gate in passthrough (nessun blocco).
    """
    _auth(token)
    if mode == "sandbox":
        return {"ok": True, "cost": 0.0, "sandbox": True}
    cost = round(_cost(tool) * _markup(), 2)
    if cost <= 0:
        return {"ok": True, "cost": 0.0, "free": True}
    from thanatos_intel.billing.mmos_wallet import mmos_balance
    bal = mmos_balance()
    if bal < cost:
        return {"ok": False, "cost": cost, "balance": bal,
                "reason": ("Saldo wallet MMOS insufficiente per openapi:%s — servono "
                           "€%.2f, disponibili €%.2f. Ricarica su cloud.onekeyco.com "
                           "oppure approva e paga manualmente." % (tool, cost, bal))}
    return {"ok": True, "cost": cost, "balance": bal}


@frappe.whitelist(allow_guest=True)
def charge(tool, token=None, ref=None, mode=None):
    """Addebito post-successo sul wallet MMOS. In sandbox non addebita."""
    _auth(token)
    if mode == "sandbox":
        return {"ok": True, "charged": 0.0, "sandbox": True}
    cost = round(_cost(tool) * _markup(), 2)
    if cost <= 0:
        return {"ok": True, "charged": 0.0}
    from thanatos_intel.billing.mmos_wallet import mmos_charge
    bal = mmos_charge(cost, notes="openapi MCP: %s" % tool, ref_name=ref or "")
    frappe.db.commit()
    return {"ok": True, "charged": cost, "balance": bal}
