"""Auto-set einvoice_profile su Sales Invoice dalla company,
   e imposta default_einvoice_profile su nuove Company in base al paese."""

import frappe

# Profilo di default per zona geografica
_EU_PROFILE = "EN 16931"
_DEFAULT_PROFILE = "BASIC"

# Mappa paese → profilo
_COUNTRY_PROFILE = {
    "Italy": "EN 16931",
    "Romania": "EN 16931",
    "Germany": "XRECHNUNG",
    "France": "EN 16931",
    "Austria": "EN 16931",
    "Belgium": "EN 16931",
    "Netherlands": "EN 16931",
    "Spain": "EN 16931",
    "Poland": "EN 16931",
}


def on_sales_invoice_before_insert(doc, method=None):
    """Imposta einvoice_profile se non già impostato."""
    if not doc.einvoice_profile and doc.company:
        profile = _get_company_profile(doc.company)
        if profile:
            doc.einvoice_profile = profile


def on_sales_invoice_validate(doc, method=None):
    """Garantisce einvoice_profile sempre impostato."""
    if not doc.einvoice_profile and doc.company:
        profile = _get_company_profile(doc.company)
        if profile:
            doc.einvoice_profile = profile


def on_company_after_insert(doc, method=None):
    """Imposta default_einvoice_profile sulla nuova company."""
    profile = _COUNTRY_PROFILE.get(doc.country or "", _DEFAULT_PROFILE)
    frappe.db.set_value("Company", doc.name, "default_einvoice_profile", profile, update_modified=False)


def _get_company_profile(company_name: str) -> str:
    profile = frappe.db.get_value("Company", company_name, "default_einvoice_profile")
    if profile:
        return profile
    country = frappe.db.get_value("Company", company_name, "country") or ""
    return _COUNTRY_PROFILE.get(country, _DEFAULT_PROFILE)
