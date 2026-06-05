"""Missing-fields engine: confronta OCR output vs profilo richiesto.

API legacy `compare(required_fields, extracted_fields)` preservata.
Nuova API `evaluate(document_type, ocr_output)` integra document_profile.
"""
from __future__ import annotations
from typing import Iterable, Mapping

from . import document_profile, risk_rules


def compare(required_fields, extracted_fields):
    """Restituisce i campi required NON presenti negli extracted (API legacy)."""
    if isinstance(extracted_fields, Mapping):
        keys = {k for k, v in extracted_fields.items() if _has_value(v)}
    elif extracted_fields is None:
        keys = set()
    elif isinstance(extracted_fields, Iterable) and not isinstance(extracted_fields, str):
        keys = set(extracted_fields)
    else:
        keys = set()
    return [f for f in required_fields if f not in keys]


def evaluate(document_type: str, ocr_output: Mapping) -> dict:
    """Pipeline completo per un documento.

    Args:
      document_type: "Passport", "Diplomatic Passport", ...
      ocr_output: dict campi estratti (es. {"number":"...","expiry_date":"..."})

    Returns:
      dict { document_type, required_fields, present_fields, missing_fields,
             completeness (0..1), expired, near_expiry, risk_score, risk_level,
             risk_flags }
    """
    required = document_profile.get_required_fields(document_type)
    meta = document_profile.get_profile_meta(document_type)

    if isinstance(ocr_output, Mapping):
        present = [k for k in required if _has_value(ocr_output.get(k))]
    else:
        present = []

    missing = [k for k in required if k not in present]
    completeness = (len(present) / len(required)) if required else 1.0

    expiry = (ocr_output or {}).get("expiry_date") if isinstance(ocr_output, Mapping) else None
    expired = risk_rules.is_document_expired(expiry)
    near_expiry = (not expired) and risk_rules.is_document_near_expiry(expiry)

    flags = risk_rules.detect_risk_flags(
        missing_fields=bool(missing),
        expired_document=expired,
    )
    if near_expiry:
        flags.append("near_expiry_document")
    if meta.get("has_mrz") and isinstance(ocr_output, Mapping) and ocr_output.get("mrz_checksum_valid") is False:
        flags.append("mrz_checksum_invalid")

    scored = risk_rules.score_flags(flags)

    return {
        "document_type": document_type,
        "required_fields": required,
        "present_fields": present,
        "missing_fields": missing,
        "completeness": round(completeness, 3),
        "expired": expired,
        "near_expiry": near_expiry,
        "risk_score": scored["score"],
        "risk_level": scored["level"],
        "risk_flags": scored["flags"],
        "blocking": scored["blocking"],
    }


def _has_value(v):
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) > 0
    return True
