"""Document profiles and required fields for visa workflows."""

DOCUMENT_TYPES = {
    "Passport": ["number", "expiry_date", "country", "full_name"],
    "Residence Permit": ["permit_number", "expiry_date", "country", "holder_name"],
    "Marriage Certificate": ["certificate_number", "issue_date", "country", "spouse_names"],
    "Financial Proof": ["document_type", "issue_date", "amount", "currency", "holder_name"],
    "Insurance": ["policy_number", "provider", "expiry_date", "coverage_amount"],
    "Photos": ["photo_count", "format", "background"],
}


def get_supported_document_types():
    """Return supported document type names."""
    return sorted(DOCUMENT_TYPES.keys())


def get_required_fields(document_type):
    """Return required fields for a document type, empty list if unknown."""
    return DOCUMENT_TYPES.get(document_type, [])
