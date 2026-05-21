from thanatos_intel.rules.missing_fields_engine import compare


def test_compare_with_dict_extracted_fields():
    required = ["number", "expiry_date", "country"]
    extracted = {"number": "X123", "country": "IT"}
    assert compare(required, extracted) == ["expiry_date"]


def test_compare_with_list_extracted_fields():
    required = ["a", "b", "c"]
    extracted = ["a", "c"]
    assert compare(required, extracted) == ["b"]


def test_compare_no_missing_fields():
    required = ["x", "y"]
    extracted = {"x": 1, "y": 2}
    assert compare(required, extracted) == []
