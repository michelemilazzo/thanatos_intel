"""Document profile catalog — full Thanatos Intel spec.

Per ciascun tipo di documento: campi richiesti, MRZ flag, photo/liveness flag,
validità default, lingue tipiche dell'OCR. Usato da missing_fields_engine,
intake checklist, e classificatore Identity Document Intelligence.
"""
from __future__ import annotations

# Backward-compat: flat dict campi richiesti (vecchia API usata dai test e
# dall'intake legacy).
DOCUMENT_TYPES = {
    "Passport":               ["number", "expiry_date", "country", "full_name"],
    "Diplomatic Passport":    ["number", "expiry_date", "country", "full_name",
                               "issuing_authority", "diplomatic_status"],
    "Service Passport":       ["number", "expiry_date", "country", "full_name",
                               "issuing_authority"],
    "Official Passport":      ["number", "expiry_date", "country", "full_name"],
    "Emergency Passport":     ["number", "expiry_date", "country", "full_name"],
    "Travel Document":        ["number", "expiry_date", "country", "full_name",
                               "convention_reference"],
    "National ID":            ["number", "expiry_date", "country", "full_name"],
    "Driver License":         ["number", "expiry_date", "country", "full_name",
                               "categories"],
    "Residence Permit":       ["permit_number", "expiry_date", "country",
                               "holder_name", "permit_type"],
    "Visa":                   ["number", "expiry_date", "country", "full_name",
                               "visa_type", "entries"],
    "Marriage Certificate":   ["certificate_number", "issue_date", "country",
                               "spouse_names"],
    "Birth Certificate":      ["certificate_number", "issue_date", "country",
                               "person_name", "date_of_birth"],
    "Criminal Record":        ["full_name", "date_of_birth", "country",
                               "issue_date", "outcome"],
    "Proof of Address":       ["holder_name", "address", "issue_date"],
    "Financial Proof":        ["document_type", "issue_date", "amount",
                               "currency", "holder_name"],
    "Source of Funds":        ["holder_name", "amount", "currency", "origin",
                               "issue_date"],
    "Insurance":              ["policy_number", "provider", "expiry_date",
                               "coverage_amount"],
    "Photos":                 ["photo_count", "format", "background"],
    "ID Photo":               ["image_hash"],
    "Company Registry":       ["company_name", "company_number", "country",
                               "issue_date", "directors"],
    "Bank Statement":         ["account_holder", "iban", "period", "balance"],
    "Power of Attorney":      ["grantor", "attorney", "scope", "issue_date"],
    "Recommendation Letter":  ["author", "recipient", "issue_date"],
}

# Metadata avanzato per il pipeline Identity Document Intelligence.
PROFILES_META = {
    "Passport":             {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 10},
    "Diplomatic Passport":  {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 5},
    "Service Passport":     {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 5},
    "Official Passport":    {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 5},
    "Emergency Passport":   {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 1},
    "Travel Document":      {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 2},
    "National ID":          {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 10},
    "Driver License":       {"has_mrz": False, "photo": True,  "liveness": False, "validity_years": 10},
    "Residence Permit":     {"has_mrz": True,  "photo": True,  "liveness": False, "validity_years": 5},
    "Visa":                 {"has_mrz": True,  "photo": False, "liveness": False, "validity_years": 1},
    "ID Photo":             {"has_mrz": False, "photo": True,  "liveness": True,  "validity_years": 0},
}

# Lingue OCR tipiche per macro-area (mapping issuing_country → tesseract code).
LANGS_BY_COUNTRY = {
    "ITA": "ita", "ROU": "ron", "BGR": "bul", "GBR": "eng", "USA": "eng",
    "FRA": "fra", "DEU": "deu", "ESP": "spa", "PRT": "por", "NLD": "nld",
    "RUS": "rus", "UKR": "ukr", "ALB": "sqi", "TUR": "tur", "GRC": "ell",
    "ARE": "ara", "SAU": "ara", "EGY": "ara",
    "CHN": "chi_sim", "JPN": "jpn", "KOR": "kor",
    "SRB": "srp", "HRV": "hrv",
}


def get_supported_document_types():
    """Lista document type supportati (ordinata)."""
    return sorted(DOCUMENT_TYPES.keys())


def get_required_fields(document_type):
    """Campi richiesti per un tipo documento, [] se sconosciuto."""
    return list(DOCUMENT_TYPES.get(document_type, []))


def get_profile_meta(document_type):
    """Metadata (MRZ, photo, liveness, validità) per il documento."""
    return dict(PROFILES_META.get(document_type, {
        "has_mrz": False, "photo": False, "liveness": False, "validity_years": 0,
    }))


def get_tesseract_lang(country_code):
    """Tesseract lang pack code per codice paese ISO-3 (fallback 'eng')."""
    return LANGS_BY_COUNTRY.get((country_code or "").upper(), "eng")
