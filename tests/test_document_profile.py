from thanatos_intel.rules.document_profile import DOCUMENT_TYPES, get_required_fields, get_supported_document_types


def test_document_types_include_expected_entries():
    expected = {
        "Passport",
        "Residence Permit",
        "Marriage Certificate",
        "Financial Proof",
        "Insurance",
        "Photos",
    }
    assert expected.issubset(set(DOCUMENT_TYPES.keys()))


def test_get_supported_document_types_sorted():
    types = get_supported_document_types()
    assert types == sorted(types)
    assert "Passport" in types


def test_get_required_fields_returns_empty_for_unknown():
    assert get_required_fields("Unknown") == []
