"""Risk rule engine — segnali di rischio normalizzati con peso e categoria.

Combina i red-flag della spec MMOS-THANATOS-2026 (KYC/KYB/Diplomatic DD) e
restituisce sia la lista flat (API legacy `detect_risk_flags`) sia uno score
0–100 con livello (low/medium/high/critical/blocked) per il rollup Risk Score.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Iterable, Optional

# Catalogo segnali: chiave canonica → (label, peso, categoria, blocking).
RISK_SIGNALS = {
    "expired_document":           ("Document expired",                   25, "document",    False),
    "near_expiry_document":       ("Document near expiry (<6 months)",   10, "document",    False),
    "missing_fields":             ("OCR returned incomplete fields",     15, "document",    False),
    "duplicate_document":         ("Duplicate document detected",        20, "document",    False),
    "country_mismatch":           ("Country mismatch in document chain", 15, "document",    False),
    "mrz_checksum_invalid":       ("MRZ checksum invalid",               30, "document",    False),
    "photo_mismatch":             ("Photo doesn't match other documents",25, "identity",    False),
    "liveness_failed":            ("Liveness check failed",              30, "identity",    False),
    "pep_declared":               ("Politically Exposed Person declared",20, "compliance",  False),
    "pep_match_high":             ("PEP screening high-confidence match",30, "compliance",  False),
    "sanctions_declared":         ("Sanctions exposure declared",        40, "compliance",  False),
    "sanctions_match_confirmed":  ("Sanctions match confirmed",         100, "compliance",  True),
    "criminal_issue_declared":    ("Criminal proceeding declared",       30, "compliance",  False),
    "previous_refusal":           ("Previous visa/passport refusal",     15, "compliance",  False),
    "bank_account_closure":       ("Bank account closure declared",      15, "financial",   False),
    "missing_source_of_funds":    ("Source of funds missing/unclear",    20, "financial",   False),
    "high_risk_country":          ("High-risk jurisdiction involved",    20, "geopolitical",False),
    "incomplete_kyc":             ("Identity verification incomplete",   25, "identity",    False),
    "adverse_media":              ("Adverse media findings",             25, "compliance",  False),
    "inconsistent_answers":       ("Inconsistent questionnaire answers", 20, "behavioural", False),
    "unclear_intermediary":       ("Unclear intermediary role",          15, "compliance",  False),
    "crypto_payment_red_flag":    ("Crypto payment with no provenance",  25, "financial",   False),
    "high_risk_pattern_en590":    ("Matches EN590 advance-fee pattern", 100, "fraud",       True),
}

# Soglie score → livello.
THRESHOLDS = [
    (0,   20, "low"),
    (21,  50, "medium"),
    (51,  75, "high"),
    (76,  99, "critical"),
    (100, 1_000_000, "blocked"),
]


def detect_risk_flags(*, missing_fields=None, expired_document=False,
                      duplicate_document=False, country_mismatch=False,
                      mrz_checksum_invalid=False, photo_mismatch=False,
                      liveness_failed=False, pep_declared=False,
                      sanctions_declared=False, sanctions_match_confirmed=False,
                      criminal_issue_declared=False, previous_refusal=False,
                      bank_account_closure=False, missing_source_of_funds=False,
                      high_risk_country=False, incomplete_kyc=False,
                      adverse_media=False, inconsistent_answers=False,
                      unclear_intermediary=False, crypto_payment_red_flag=False,
                      high_risk_pattern_en590=False, **kwargs):
    """Restituisce la lista flat dei flag (API legacy preservata)."""
    locals_ = locals()
    flags = []
    for k in RISK_SIGNALS:
        if locals_.get(k):
            flags.append(k)
    if missing_fields:
        flags.append("missing_fields")
    # Preserva ordine deterministico (definizione catalog).
    order = list(RISK_SIGNALS.keys())
    return sorted(set(flags), key=lambda x: order.index(x) if x in order else 999)


def score_flags(flags: Iterable[str]) -> dict:
    """Calcola score (0–100) e livello da una lista di flag."""
    flags = list(flags)
    blocking = any(RISK_SIGNALS.get(f, ("", 0, "", False))[3] for f in flags)
    raw = sum(RISK_SIGNALS.get(f, ("", 0, "", False))[1] for f in flags)
    score = 100 if blocking else min(100, raw)
    level = _level_for(score)
    return {
        "score": score,
        "level": level,
        "blocking": blocking,
        "flags": flags,
        "details": [
            {"flag": f, "label": RISK_SIGNALS[f][0],
             "weight": RISK_SIGNALS[f][1], "category": RISK_SIGNALS[f][2]}
            for f in flags if f in RISK_SIGNALS
        ],
    }


def _level_for(score: int) -> str:
    for lo, hi, label in THRESHOLDS:
        if lo <= score <= hi:
            return label
    return "low"


def is_document_expired(expiry: Optional[str | date]) -> bool:
    """True se la data di scadenza è nel passato."""
    if not expiry:
        return False
    d = expiry if isinstance(expiry, date) else _parse_date(expiry)
    return bool(d and d < date.today())


def is_document_near_expiry(expiry: Optional[str | date], months: int = 6) -> bool:
    """True se la scadenza è entro N mesi (default 6)."""
    if not expiry:
        return False
    d = expiry if isinstance(expiry, date) else _parse_date(expiry)
    if not d:
        return False
    delta_days = (d - date.today()).days
    return 0 <= delta_days <= months * 30


def _parse_date(s):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None
