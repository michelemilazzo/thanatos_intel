from thanatos_intel.rules.country_rules import (
    COUNTRY_RULES, get_country_rule,
    DIPLOMATIC_FRAMEWORK, get_diplomatic_framework,
    list_supported_countries, list_diplomatic_countries,
)


def test_known_country_rule_exists():
    rule = get_country_rule("Italy")
    assert "required_documents" in rule
    assert "Passport" in rule["required_documents"]
    assert rule["iso3"] == "ITA"


def test_generic_fallback_is_used_for_unknown_country():
    unknown = get_country_rule("Neverland")
    assert unknown == COUNTRY_RULES["generic"]


def test_all_configured_countries_have_required_documents():
    for _, rule in COUNTRY_RULES.items():
        assert rule["required_documents"]
        assert "minimum_validity_months" in rule


def test_get_country_rule_returns_independent_copy():
    rule = get_country_rule("Italy")
    rule["required_documents"].append("MUTATED")
    assert "MUTATED" not in get_country_rule("Italy")["required_documents"]


def test_diplomatic_framework_bulgaria():
    fw = get_diplomatic_framework("Bulgaria")
    assert "Diplomatic Passport" in fw["passport_types"]
    assert fw["supports_honorary_consul"] is True
    assert "bg" in fw["official_languages"]


def test_diplomatic_framework_generic_marks_incomplete():
    fw = get_diplomatic_framework("Atlantis")
    assert "incomplete_framework" in fw["risk_indicators"]


def test_list_supported_countries_excludes_generic():
    assert "generic" not in list_supported_countries()
    assert "Italy" in list_supported_countries()


def test_list_diplomatic_countries_includes_bulgaria():
    assert "Bulgaria" in list_diplomatic_countries()
    assert "generic" not in list_diplomatic_countries()
