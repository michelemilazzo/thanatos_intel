"""Country-specific document requirements with generic fallback."""

COUNTRY_RULES = {
    "Italy": {
        "required_documents": ["Passport", "Financial Proof", "Insurance", "Photos"],
        "minimum_validity_months": 6,
    },
    "Romania": {
        "required_documents": ["Passport", "Financial Proof", "Photos"],
        "minimum_validity_months": 6,
    },
    "Sweden": {
        "required_documents": ["Passport", "Financial Proof", "Insurance", "Photos"],
        "minimum_validity_months": 6,
    },
    "Germany": {
        "required_documents": ["Passport", "Financial Proof", "Insurance", "Photos"],
        "minimum_validity_months": 6,
    },
    "generic": {
        "required_documents": ["Passport", "Financial Proof", "Photos"],
        "minimum_validity_months": 3,
    },
}


def get_country_rule(country):
    """Return country rules or generic fallback."""
    return COUNTRY_RULES.get(country, COUNTRY_RULES["generic"])
