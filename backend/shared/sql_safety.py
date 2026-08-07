"""
Guardrails for building SQL against identifiers that come from request input.

Postgres/TimescaleDB table and column identifiers cannot be bound as regular
query parameters, so any `table_name`/column/interval string that reaches an
f-string SQL query must first be validated against an allowlist here.
"""
import re

from sqlalchemy import text

_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\s+(ASC|DESC))?$", re.IGNORECASE)
_INTERVAL_RE = re.compile(
    r"^\d+\s+(day|days|hour|hours|minute|minutes|week|weeks)$", re.IGNORECASE
)


def validate_hypertable_name(conn, table_name: str) -> str:
    """
    Confirm `table_name` is a real, existing TimescaleDB hypertable before it
    is interpolated into any SQL string. Raises ValueError if not - this
    makes the allowlist self-maintaining instead of a hardcoded list that
    drifts as hypertables are added/removed.
    """
    result = conn.execute(
        text(
            "SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = :name"
        ),
        {"name": table_name},
    )
    if result.fetchone() is None:
        raise ValueError(f"Unknown hypertable: {table_name!r}")
    return table_name


def validate_column_identifier(name: str) -> str:
    """Confirm a column name (optionally with ASC/DESC) is a bare SQL identifier."""
    if not _COLUMN_RE.match(name.strip()):
        raise ValueError(f"Invalid column identifier: {name!r}")
    return name.strip()


def validate_interval_literal(value: str) -> str:
    """Confirm an interval string (e.g. "7 days") before it reaches INTERVAL '...'."""
    if not _INTERVAL_RE.match(value.strip()):
        raise ValueError(f"Invalid interval literal: {value!r}")
    return value.strip()
