"""
Centralized input validation for XSS/SQLi and injection hardening.
"""
import re
from typing import Any, Iterable, List, Pattern

XSS_PATTERNS: List[Pattern[str]] = [
    re.compile(r"(<\s*script\b|</\s*script\s*>)", re.IGNORECASE),
    re.compile(r"(onerror\s*=|onload\s*=|javascript:)", re.IGNORECASE),
    re.compile(r"(<\s*iframe\b|document\.cookie|eval\s*\()", re.IGNORECASE),
]

SQLI_PATTERNS: List[Pattern[str]] = [
    re.compile(
        r"(\bunion\b\s+\bselect\b|\bdrop\b\s+\btable\b|\binsert\b\s+\binto\b)",
        re.IGNORECASE,
    ),
    re.compile(r"(\bor\b\s+1\s*=\s*1\b|\band\b\s+1\s*=\s*1\b)", re.IGNORECASE),
    re.compile(r"(--|/\*|\*/|;\s*shutdown\b|xp_cmdshell)", re.IGNORECASE),
]

SUSPICIOUS_INPUT_PATTERNS: List[Pattern[str]] = XSS_PATTERNS + SQLI_PATTERNS


def contains_suspicious_content(
    value: str, patterns: Iterable[Pattern[str]] = None
) -> bool:
    if not value:
        return False
    active = patterns if patterns is not None else SUSPICIOUS_INPUT_PATTERNS
    return any(p.search(value) for p in active)


def scan_payload_for_attacks(payload: Any) -> bool:
    if isinstance(payload, dict):
        return any(
            contains_suspicious_content(str(k)) or scan_payload_for_attacks(v)
            for k, v in payload.items()
        )
    if isinstance(payload, list):
        return any(scan_payload_for_attacks(item) for item in payload)
    if isinstance(payload, str):
        return contains_suspicious_content(payload)
    return False


def validate_query_params(params: dict, *, max_length: int = 1024) -> List[str]:
    """Return list of validation error messages (empty if valid)."""
    errors: List[str] = []
    for key, value in params.items():
        if len(str(key)) > max_length or len(str(value)) > max_length:
            errors.append("parameter_length_exceeded")
        if contains_suspicious_content(str(key)) or contains_suspicious_content(
            str(value)
        ):
            errors.append("suspicious_query_param")
    return errors
