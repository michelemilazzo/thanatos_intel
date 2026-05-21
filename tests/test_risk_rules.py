from thanatos_intel.rules.risk_rules import detect_risk_flags


def test_detect_single_flag():
    flags = detect_risk_flags(expired_document=True)
    assert flags == ["expired_document"]


def test_detect_multiple_flags():
    flags = detect_risk_flags(missing_fields=["insurance"], duplicate_document=True, country_mismatch=True)
    assert "missing_fields" in flags
    assert "duplicate_document" in flags
    assert "country_mismatch" in flags


def test_detect_no_flags_returns_empty():
    assert detect_risk_flags() == []
