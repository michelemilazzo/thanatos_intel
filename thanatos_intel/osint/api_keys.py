"""
Gestione chiavi API OSINT — Thanatos Intel.

Pagina operatore (System Manager) per inserire le API key gratuite delle fonti
`needs_key` e salvarle in site_config. Espone i link di registrazione dove
ottenere ciascuna chiave.

Sicurezza:
- solo System Manager;
- si possono scrivere SOLO le config key dichiarate dal registry (whitelist);
- il valore salvato non viene MAI restituito: si espone solo lo stato configurata/no.
"""
import frappe
from frappe.installer import update_site_config

from thanatos_intel.osint.source_registry import SOURCES

# Pagina di registrazione dove ottenere la API key gratuita (senza carta).
SIGNUP = {
    "abuseipdb_api_key": "https://www.abuseipdb.com/account/api",
    "ipinfo_token": "https://ipinfo.io/signup",
    "virustotal_api_key": "https://www.virustotal.com/gui/join-us",
    "urlscan_api_key": "https://urlscan.io/user/signup/",
    "shodan_api_key": "https://account.shodan.io/register",
    "censys_api_id": "https://accounts.censys.io/register",
    "securitytrails_api_key": "https://securitytrails.com/app/signup",
    "opencorporates_api_key": "https://opencorporates.com/api_accounts/new",
    "companies_house_api_key": "https://developer.company-information.service.gov.uk/get-started",
    "etherscan_api_key": "https://etherscan.io/register",
    "viewdns_api_key": "https://viewdns.info/api/",
    "greynoise_api_key": "https://www.greynoise.io/signup",
    "otx_api_key": "https://otx.alienvault.com/",
    "pulsedive_api_key": "https://pulsedive.com/signup/",
    "mapillary_token": "https://www.mapillary.com/dashboard/developers",
}

# Fonti che richiedono una seconda credenziale.
EXTRA_KEYS = {
    "censys_api_id": [("censys_api_secret", "Censys API Secret")],
}

# Whitelist: solo queste config key sono scrivibili da questa pagina.
ALLOWED = ({s["needs"] for s in SOURCES if s.get("needs")}
           | {ek for lst in EXTRA_KEYS.values() for ek, _ in lst})


def _require_admin():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Riservato a System Manager", frappe.PermissionError)


@frappe.whitelist()
def key_sources() -> list:
    """Elenco fonti che richiedono una API key, con link registrazione e stato."""
    _require_admin()
    out, seen = [], set()
    for s in SOURCES:
        k = s.get("needs")
        if not k or k in seen:
            continue
        if s.get("tier") == "paid":          # fonti a pagamento: escluse dalla pagina
            continue
        seen.add(k)
        out.append({
            "name": s["name"],
            "config_key": k,
            "category": s["category"],
            "tier": s["tier"],
            "homepage": s.get("url"),
            "signup": SIGNUP.get(k, s.get("url")),
            "configured": bool(frappe.conf.get(k)),
            "extra": [{"config_key": ek, "label": lbl,
                       "configured": bool(frappe.conf.get(ek))}
                      for ek, lbl in EXTRA_KEYS.get(k, [])],
        })
    return out


@frappe.whitelist()
def save_api_key(config_key: str, value: str) -> dict:
    """Salva una API key in site_config (whitelist + System Manager)."""
    _require_admin()
    config_key = (config_key or "").strip()
    if config_key not in ALLOWED:
        frappe.throw("Config key non consentita")
    value = (value or "").strip()
    if not value:
        frappe.throw("Valore vuoto")
    update_site_config(config_key, value)
    frappe.clear_cache()
    return {"ok": True, "config_key": config_key, "configured": True}


@frappe.whitelist()
def clear_api_key(config_key: str) -> dict:
    """Rimuove una API key da site_config."""
    _require_admin()
    config_key = (config_key or "").strip()
    if config_key not in ALLOWED:
        frappe.throw("Config key non consentita")
    update_site_config(config_key, None)
    frappe.clear_cache()
    return {"ok": True, "config_key": config_key, "configured": False}
