from __future__ import annotations

import re

from core.data.schema import SchemaMetadata
from core.data.validators.base import ValidationResult

_FROM_JOIN = re.compile(r"\b(?:FROM|JOIN)\s+(?:ONLY\s+)?([\"`]?)([a-zA-Z_][\w$]*)\1", re.IGNORECASE)
_QUALIFIED = re.compile(r"\b([a-zA-Z_][\w$]*)\.([a-zA-Z_][\w$]*)\b")
_RESERVED = {
    "select",
    "where",
    "group",
    "order",
    "by",
    "as",
    "on",
    "and",
    "or",
    "not",
    "null",
    "true",
    "false",
    "case",
    "when",
    "then",
    "else",
    "end",
    "limit",
    "offset",
    "having",
    "distinct",
    "with",
    "union",
    "all",
    "inner",
    "left",
    "right",
    "full",
    "cross",
    "join",
    "from",
}


def validate_sql_against_schema(sql: str, schema: SchemaMetadata) -> ValidationResult:
    """Check that referenced tables and qualified columns exist in schema metadata."""
    if not schema.tables:
        return ValidationResult(ok=True)

    tables = {t.name.lower(): t for t in schema.tables}
    columns_by_table = {name: {c.name.lower() for c in table.columns} for name, table in tables.items()}

    referenced_tables: set[str] = set()
    for _quote, table_name in _FROM_JOIN.findall(sql):
        key = table_name.lower()
        referenced_tables.add(key)
        if key not in tables:
            available = ", ".join(sorted(tables))
            return ValidationResult(
                ok=False,
                error=f"Unknown table '{table_name}'. Available tables: {available or 'none'}.",
            )

    if not referenced_tables:
        return ValidationResult(ok=False, error="Could not determine which table(s) the query uses.")

    for table_ref, column_ref in _QUALIFIED.findall(sql):
        table_key = table_ref.lower()
        column_key = column_ref.lower()
        if table_key in _RESERVED:
            continue
        if table_key not in tables:
            continue
        if column_key not in columns_by_table[table_key]:
            available = ", ".join(sorted(columns_by_table[table_key]))
            return ValidationResult(
                ok=False,
                error=(
                    f"Column '{table_ref}.{column_ref}' is not in the schema. "
                    f"Columns on {table_ref}: {available}."
                ),
            )

    return ValidationResult(ok=True)
