from app.core.validation import STRICT_PATTERNS, validate_value


def test_validate_value_accepts_compressed_ipv6():
    result = validate_value("observable.IP", "2606:4700:3037::ac43:ddb4")

    assert result.valid is True
    assert result.error is None


def test_strict_ipv6_pattern_accepts_compressed_ipv6():
    assert STRICT_PATTERNS["ipv6"].match("2606:4700:3037::ac43:ddb4")