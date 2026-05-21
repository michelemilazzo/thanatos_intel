"""Basic risk signal detection for intake documents."""


def detect_risk_flags(*, missing_fields=None, expired_document=False, duplicate_document=False, country_mismatch=False):
    """Collect normalized risk flags based on document review signals."""
    flags = []

    if expired_document:
        flags.append("expired_document")
    if missing_fields:
        flags.append("missing_fields")
    if duplicate_document:
        flags.append("duplicate_document")
    if country_mismatch:
        flags.append("country_mismatch")

    return flags
