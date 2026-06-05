from datetime import date, timedelta

from thanatos_intel.rules.risk_rules import (
    detect_risk_flags, score_flags, RISK_SIGNALS,
    is_document_expired, is_document_near_expiry,
)


def test_detect_single_flag():
    flags = detect_risk_flags(expired_document=True)
    assert flags == ["expired_document"]


def test_detect_multiple_flags():
    flags = detect_risk_flags(missing_fields=["insurance"],
                              duplicate_document=True, country_mismatch=True)
    assert "missing_fields" in flags
    assert "duplicate_document" in flags
    assert "country_mismatch" in flags


def test_detect_no_flags_returns_empty():
    assert detect_risk_flags() == []


def test_score_blocking_sanctions_match():
    s = score_flags(["sanctions_match_confirmed"])
    assert s["blocking"] is True
    assert s["level"] == "blocked"
    assert s["score"] == 100


def test_score_medium_level():
    s = score_flags(["expired_document", "missing_fields"])  # 25+15=40
    assert s["level"] == "medium"
    assert s["score"] == 40


def test_score_high_level():
    s = score_flags(["pep_declared", "criminal_issue_declared",
                     "missing_source_of_funds"])  # 20+30+20 = 70
    assert s["level"] == "high"


def test_all_signals_have_catalog_entry():
    for k, (label, weight, cat, blocking) in RISK_SIGNALS.items():
        assert label, k
        assert weight >= 0
        assert cat in ("document", "identity", "compliance", "financial",
                       "geopolitical", "behavioural", "fraud")


def test_is_document_expired():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert is_document_expired(yesterday) is True
    assert is_document_expired(tomorrow) is False
    assert is_document_expired(None) is False


def test_is_document_near_expiry():
    in_3_months = (date.today() + timedelta(days=90)).isoformat()
    in_2_years = (date.today() + timedelta(days=730)).isoformat()
    assert is_document_near_expiry(in_3_months) is True
    assert is_document_near_expiry(in_2_years) is False
