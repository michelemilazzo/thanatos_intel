"""Utility to identify missing fields from OCR extraction."""


def compare(required_fields, extracted_fields):
    """Return required fields not found in extracted field keys."""
    extracted_keys = set(extracted_fields.keys()) if isinstance(extracted_fields, dict) else set(extracted_fields or [])
    return [field for field in required_fields if field not in extracted_keys]
