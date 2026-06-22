"""Country-specific document requirements + diplomatic eligibility framework.

Usato dall'intake (visa workflow) e dal Diplomatic DD case per pre-filtrare
i documenti richiesti per paese. Tutti gli importi vanno espressi nella valuta
locale del paese di destinazione.

Layer 1 = visa/general requirements (compatibile API legacy).
Layer 2 = diplomatic_framework (estensione DDD: passaporto diplomatico, base
giuridica, autorità competente).
"""
from __future__ import annotations
import copy

# Layer 1: visa / general requirements (API legacy preservata).
COUNTRY_RULES = {
    "Italy": {
        "iso3": "ITA",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos", "Proof of Address"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 850,
    },
    "Romania": {
        "iso3": "ROU",
        "required_documents": ["Passport", "Financial Proof", "Photos",
                               "Criminal Record"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 500,
    },
    "Bulgaria": {
        "iso3": "BGR",
        "required_documents": ["Passport", "Financial Proof", "Photos",
                               "Criminal Record", "Insurance"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 600,
    },
    "Sweden": {
        "iso3": "SWE",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 1100,
    },
    "Germany": {
        "iso3": "DEU",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos", "Proof of Address"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 1027,
    },
    "France": {
        "iso3": "FRA",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 900,
    },
    "Spain": {
        "iso3": "ESP",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 800,
    },
    "Portugal": {
        "iso3": "PRT",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 760,
    },
    "Netherlands": {
        "iso3": "NLD",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 1100,
    },
    "United Kingdom": {
        "iso3": "GBR",
        "required_documents": ["Passport", "Financial Proof", "Insurance",
                               "Photos"],
        "minimum_validity_months": 6,
        "min_funds_eur_per_month": 1200,
    },
    "generic": {
        "iso3": None,
        "required_documents": ["Passport", "Financial Proof", "Photos"],
        "minimum_validity_months": 3,
        "min_funds_eur_per_month": 500,
    },
}


# Layer 2: diplomatic eligibility framework (DDD module).
DIPLOMATIC_FRAMEWORK = {
    "Bulgaria": {
        "passport_types": ["Diplomatic Passport", "Service Passport",
                           "Official Passport", "Ordinary Passport"],
        "official_languages": ["bg", "en"],
        "issuing_authority": "Ministry of Foreign Affairs of Bulgaria",
        "legal_basis": "Bulgaria Law on Bulgarian Identity Documents, Art. 38",
        "diplomatic_representation": True,
        "consular_presence": True,
        "risk_indicators": ["pep_high_priority", "sanctions_review_required"],
        "min_due_diligence_days": 30,
        "supports_honorary_consul": True,
    },
    "Romania": {
        "passport_types": ["Diplomatic Passport", "Service Passport",
                           "Ordinary Passport"],
        "official_languages": ["ro", "en"],
        "issuing_authority": "Ministry of Foreign Affairs of Romania",
        "legal_basis": "Law 248/2005 on the free movement of citizens",
        "diplomatic_representation": True,
        "consular_presence": True,
        "risk_indicators": ["pep_review_required"],
        "min_due_diligence_days": 30,
        "supports_honorary_consul": True,
    },
    "Italy": {
        "passport_types": ["Diplomatic Passport", "Service Passport",
                           "Ordinary Passport"],
        "official_languages": ["it", "en"],
        "issuing_authority": "Ministero degli Affari Esteri e della Cooperazione Internazionale",
        "legal_basis": "Legge 21 novembre 1967, n. 1185",
        "diplomatic_representation": True,
        "consular_presence": True,
        "risk_indicators": [],
        "min_due_diligence_days": 45,
        "supports_honorary_consul": True,
    },
    "generic": {
        "passport_types": ["Ordinary Passport"],
        "official_languages": ["en"],
        "issuing_authority": "Competent National Authority",
        "legal_basis": "Applicable national law of the issuing country",
        "diplomatic_representation": False,
        "consular_presence": False,
        "risk_indicators": ["incomplete_framework"],
        "min_due_diligence_days": 60,
        "supports_honorary_consul": False,
    },
}


def get_country_rule(country):
    """Visa/general rule per paese (API legacy)."""
    return copy.deepcopy(COUNTRY_RULES.get(country, COUNTRY_RULES["generic"]))


def get_diplomatic_framework(country):
    """Framework DDD per paese; fallback 'generic' con risk indicator."""
    return copy.deepcopy(DIPLOMATIC_FRAMEWORK.get(country, DIPLOMATIC_FRAMEWORK["generic"]))


def list_supported_countries():
    """Paesi con rule esplicita (esclude fallback)."""
    return sorted(k for k in COUNTRY_RULES.keys() if k != "generic")


def list_diplomatic_countries():
    """Paesi con framework diplomatico esplicito."""
    return sorted(k for k in DIPLOMATIC_FRAMEWORK.keys() if k != "generic")
