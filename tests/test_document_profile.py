from thanatos_intel.rules.document_profile import (
    DOCUMENT_TYPES,
    get_required_fields,
    get_supported_document_types,
    get_profile_meta,
    get_tesseract_lang,
)


def test_document_types_include_expected_entries():
    expected = {
        "Passport", "Diplomatic Passport", "Service Passport",
        "Residence Permit", "Marriage Certificate",
        "Financial Proof", "Insurance", "Photos",
    }
    assert expected.issubset(set(DOCUMENT_TYPES.keys()))


def test_get_supported_document_types_sorted():
    types = get_supported_document_types()
    assert types == sorted(types)
    assert "Passport" in types
    assert "Diplomatic Passport" in types


def test_get_required_fields_returns_empty_for_unknown():
    assert get_required_fields("Unknown") == []


def test_get_required_fields_returns_copy():
    a = get_required_fields("Passport")
    a.append("mutated")
    assert "mutated" not in get_required_fields("Passport")


def test_passport_meta_has_mrz_and_photo():
    m = get_profile_meta("Passport")
    assert m["has_mrz"] is True
    assert m["photo"] is True
    assert m["validity_years"] == 10


def test_tesseract_lang_mapping():
    assert get_tesseract_lang("ITA") == "ita"
    assert get_tesseract_lang("ROU") == "ron"
    assert get_tesseract_lang("BGR") == "bul"
    assert get_tesseract_lang("CHN") == "chi_sim"
    assert get_tesseract_lang("XYZ") == "eng"
    assert get_tesseract_lang(None) == "eng"
