from thanatos_intel.rules.country_rules import COUNTRY_RULES, get_country_rule


def test_known_country_rule_exists():
    rule = get_country_rule("Italy")
    assert "required_documents" in rule
    assert "Passport" in rule["required_documents"]


def test_generic_fallback_is_used_for_unknown_country():
    unknown = get_country_rule("Neverland")
    assert unknown == COUNTRY_RULES["generic"]


def test_all_configured_countries_have_required_documents():
    for _, rule in COUNTRY_RULES.items():
        assert rule["required_documents"]
