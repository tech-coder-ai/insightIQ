from __future__ import annotations

import re

from core.data.validators.base import ValidationResult

DESTRUCTIVE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|MERGE|CALL|ALTER|GRANT|REVOKE|CREATE|REPLACE)\b",
    re.IGNORECASE,
)

_LEADING_COMMENT = re.compile(r"^\s*(--[^\n]*\n|/\*.*?\*/|\s)+", re.DOTALL)


def _strip_leading_comments(sql: str) -> str:
    return _LEADING_COMMENT.sub("", sql, count=1)


def check_readonly_select(sql: str) -> ValidationResult:
    """Static guard for warehouse dialects where a live EXPLAIN is undesirable.

    Ensures the statement is a single read-only SELECT/WITH and contains no
    destructive keywords. This runs before the query is sent to the engine.
    """
    stripped = _strip_leading_comments(sql).strip().rstrip(";").strip()
    if not stripped:
        return ValidationResult(ok=False, error="empty query")

    if DESTRUCTIVE.search(stripped):
        return ValidationResult(ok=False, error="destructive SQL is not allowed")

    first_word = stripped.split(None, 1)[0].upper()
    if first_word not in {"SELECT", "WITH"}:
        return ValidationResult(ok=False, error="only read-only SELECT queries are allowed")

    # Disallow stacked statements (a second statement after a semicolon).
    if ";" in stripped:
        return ValidationResult(ok=False, error="multiple statements are not allowed")

    return ValidationResult(ok=True)
