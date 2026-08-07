"""Unit tests for shared.input_validation."""
import pytest

from shared.input_validation import (
    contains_suspicious_content,
    scan_payload_for_attacks,
    validate_query_params,
)


@pytest.mark.unit
def test_contains_suspicious_content_detects_xss():
    assert contains_suspicious_content("<script>alert(1)</script>") is True
    assert contains_suspicious_content("javascript:alert(1)") is True
    assert contains_suspicious_content("normal-value") is False
    assert contains_suspicious_content("") is False


@pytest.mark.unit
def test_contains_suspicious_content_detects_sqli():
    assert contains_suspicious_content("1 OR 1=1") is True
    assert contains_suspicious_content("'; DROP TABLE users;--") is True
    assert contains_suspicious_content("well_name=PROD-001") is False


@pytest.mark.unit
def test_scan_payload_for_attacks_nested():
    assert scan_payload_for_attacks({"name": "ok", "nested": {"x": "<script>"}}) is True
    assert scan_payload_for_attacks({"items": ["a", "b"]}) is False
    assert scan_payload_for_attacks(["safe", "values"]) is False


@pytest.mark.unit
def test_validate_query_params():
    assert validate_query_params({"well": "PROD-001"}) == []
    errors = validate_query_params({"q": "<script>"})
    assert "suspicious_query_param" in errors


@pytest.mark.unit
def test_scan_payload_non_string_returns_false():
    assert scan_payload_for_attacks(42) is False
    assert scan_payload_for_attacks(None) is False
    assert scan_payload_for_attacks(3.14) is False


@pytest.mark.unit
def test_validate_query_params_length_exceeded():
    long_val = "x" * 2000
    errors = validate_query_params({"q": long_val}, max_length=1024)
    assert "parameter_length_exceeded" in errors
