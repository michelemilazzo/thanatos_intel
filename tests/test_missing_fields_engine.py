from datetime import date, timedelta

from thanatos_intel.rules.missing_fields_engine import compare, evaluate


def test_compare_with_dict_extracted_fields():
    required = ["number", "expiry_date", "country"]
    extracted = {"number": "X123", "country": "IT"}
    assert compare(required, extracted) == ["expiry_date"]


def test_compare_treats_empty_string_as_missing():
    required = ["number", "expiry_date"]
    extracted = {"number": "  ", "expiry_date": "2030-01-01"}
    assert "number" in compare(required, extracted)


def test_compare_with_list_extracted_fields():
    required = ["a", "b", "c"]
    extracted = ["a", "c"]
    assert compare(required, extracted) == ["b"]


def test_compare_no_missing_fields():
    required = ["x", "y"]
    extracted = {"x": 1, "y": 2}
    assert compare(required, extracted) == []


def test_compare_none_extracted_returns_all_required_missing():
    assert compare(["a", "b"], None) == ["a", "b"]


def test_evaluate_complete_passport():
    expiry = (date.today() + timedelta(days=365 * 5)).isoformat()
    ocr = {"number": "AA000000", "expiry_date": expiry,
           "country": "ITA", "full_name": "Mario Rossi"}
    out = evaluate("Passport", ocr)
    assert out["missing_fields"] == []
    assert out["completeness"] == 1.0
    assert out["expired"] is False
    assert out["risk_level"] in ("low", "medium")
    assert out["blocking"] is False


def test_evaluate_expired_passport_raises_risk():
    expired = (date.today() - timedelta(days=30)).isoformat()
    ocr = {"number": "AA000000", "expiry_date": expired,
           "country": "ITA", "full_name": "Mario Rossi"}
    out = evaluate("Passport", ocr)
    assert out["expired"] is True
    assert "expired_document" in out["risk_flags"]
    assert out["risk_score"] >= 25


def test_evaluate_missing_fields_flagged():
    ocr = {"number": "AA000000"}
    out = evaluate("Passport", ocr)
    assert "expiry_date" in out["missing_fields"]
    assert "missing_fields" in out["risk_flags"]
    assert out["completeness"] < 1.0


def test_evaluate_near_expiry_passport():
    near = (date.today() + timedelta(days=60)).isoformat()
    ocr = {"number": "AA000000", "expiry_date": near,
           "country": "ITA", "full_name": "Mario Rossi"}
    out = evaluate("Passport", ocr)
    assert out["near_expiry"] is True
    assert "near_expiry_document" in out["risk_flags"]


def test_evaluate_mrz_checksum_invalid_flag():
    expiry = (date.today() + timedelta(days=365)).isoformat()
    ocr = {"number": "AA1", "expiry_date": expiry, "country": "ITA",
           "full_name": "X Y", "mrz_checksum_valid": False}
    out = evaluate("Passport", ocr)
    assert "mrz_checksum_invalid" in out["risk_flags"]
