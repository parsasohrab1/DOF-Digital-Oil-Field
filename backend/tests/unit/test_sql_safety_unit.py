"""
Tests for shared.sql_safety: the allowlist guardrails that stand between
user-controlled strings and f-string-interpolated SQL identifiers.
"""

import pytest

from shared.sql_safety import (
    validate_column_identifier,
    validate_hypertable_name,
    validate_interval_literal,
)


class TestValidateColumnIdentifier:
    def test_accepts_bare_identifier(self):
        assert validate_column_identifier("pressure") == "pressure"

    def test_accepts_identifier_with_underscore_and_digits(self):
        assert validate_column_identifier("sensor_id_2") == "sensor_id_2"

    def test_accepts_identifier_with_direction_suffix(self):
        assert validate_column_identifier("value DESC") == "value DESC"
        assert validate_column_identifier("value ASC") == "value ASC"

    def test_strips_surrounding_whitespace(self):
        assert validate_column_identifier("  pressure  ") == "pressure"

    @pytest.mark.parametrize(
        "payload",
        [
            "value; DROP TABLE sensor_data;--",
            "value' OR '1'='1",
            "value/**/OR/**/1=1",
            "(SELECT password FROM users)",
            "value, (SELECT 1)",
            "1value",  # cannot start with a digit
            "value--comment",
            "",
            "value DESC; DROP TABLE x",
        ],
    )
    def test_rejects_sql_injection_payloads(self, payload):
        with pytest.raises(ValueError):
            validate_column_identifier(payload)


class TestValidateIntervalLiteral:
    @pytest.mark.parametrize(
        "value",
        [
            "7 days",
            "1 day",
            "24 hours",
            "1 hour",
            "30 minutes",
            "1 minute",
            "2 weeks",
            "1 week",
        ],
    )
    def test_accepts_well_formed_intervals(self, value):
        assert validate_interval_literal(value) == value

    @pytest.mark.parametrize(
        "payload",
        [
            "7 days; DROP TABLE sensor_data;--",
            "7 days' OR '1'='1",
            "1; SELECT pg_sleep(10)",
            "abc days",
            "7",
            "days",
            "",
            "7 fortnights",
        ],
    )
    def test_rejects_sql_injection_and_malformed_intervals(self, payload):
        with pytest.raises(ValueError):
            validate_interval_literal(payload)


class TestValidateHypertableName:
    def test_accepts_name_that_exists_in_hypertables_view(self):
        class FakeResult:
            def fetchone(self):
                return (1,)

        class FakeConn:
            def execute(self, *args, **kwargs):
                return FakeResult()

        assert validate_hypertable_name(FakeConn(), "sensor_data") == "sensor_data"

    def test_rejects_name_not_present_in_hypertables_view(self):
        class FakeResult:
            def fetchone(self):
                return None

        class FakeConn:
            def execute(self, *args, **kwargs):
                return FakeResult()

        with pytest.raises(ValueError):
            validate_hypertable_name(FakeConn(), "pg_shadow")

    def test_query_uses_bound_parameter_not_string_interpolation(self):
        """The table name must travel as a bound param (:name), never
        f-string-interpolated into the SQL text itself -- otherwise this
        guardrail would just move the injection point rather than closing it."""
        captured = {}

        class FakeResult:
            def fetchone(self):
                return (1,)

        class FakeConn:
            def execute(self, stmt, params=None):
                captured["sql_text"] = str(stmt)
                captured["params"] = params
                return FakeResult()

        malicious_name = "sensor_data; DROP TABLE users;--"
        validate_hypertable_name(FakeConn(), malicious_name)

        assert malicious_name not in captured["sql_text"]
        assert captured["params"] == {"name": malicious_name}
