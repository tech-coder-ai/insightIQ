from __future__ import annotations

from typing import Any

from core.data.schema import SchemaMetadata, TableMeta


def default_scope_from_schema(schema: SchemaMetadata) -> dict[str, Any]:
    """Select every table and column discovered during introspection."""
    return {"tables": {t.name: [c.name for c in t.columns] for t in schema.tables}}


def normalize_scope(scope: dict[str, Any] | None) -> dict[str, list[str]] | None:
    if not scope:
        return None
    raw = scope.get("tables") if isinstance(scope.get("tables"), dict) else scope
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, list[str]] = {}
    for table, columns in raw.items():
        name = str(table).strip()
        if not name:
            continue
        if columns is None or columns == ["*"]:
            out[name] = []
            continue
        if isinstance(columns, list):
            out[name] = [str(c).strip() for c in columns if str(c).strip()]
        else:
            out[name] = []
    return out or None


def apply_selected_scope(schema: SchemaMetadata, scope: dict[str, Any] | None) -> SchemaMetadata:
    """Filter schema metadata to the tables/columns the user selected."""
    tables_map = normalize_scope(scope)
    if not tables_map:
        return schema

    selected_tables: list[TableMeta] = []
    for table in schema.tables:
        if table.name not in tables_map:
            continue
        allowed = tables_map[table.name]
        if not allowed:
            selected_tables.append(table)
            continue
        allowed_set = set(allowed)
        filtered_cols = [c for c in table.columns if c.name in allowed_set]
        if filtered_cols:
            selected_tables.append(
                TableMeta(name=table.name, columns=filtered_cols, indexes=table.indexes)
            )

    selected_names = {t.name for t in selected_tables}
    selected_columns = {(t.name, c.name) for t in selected_tables for c in t.columns}
    relationships = [
        r
        for r in schema.relationships
        if r.from_table in selected_names
        and r.to_table in selected_names
        and (r.from_table, r.from_column) in selected_columns
        and (r.to_table, r.to_column) in selected_columns
    ]
    return SchemaMetadata(tables=selected_tables, relationships=relationships)


def scope_counts(schema_json: dict[str, Any] | None, scope_json: dict[str, Any] | None) -> tuple[int, int]:
    schema = SchemaMetadata.model_validate(schema_json or {"tables": []})
    scoped = apply_selected_scope(schema, scope_json)
    tables = len(scoped.tables)
    columns = sum(len(t.columns) for t in scoped.tables)
    return tables, columns


def scope_to_storage(scope: dict[str, Any] | None, schema: SchemaMetadata) -> dict[str, Any]:
    normalized = normalize_scope(scope)
    if normalized is None:
        return default_scope_from_schema(schema)
    cleaned: dict[str, list[str]] = {}
    schema_tables = {t.name: t for t in schema.tables}
    for table_name, columns in normalized.items():
        table = schema_tables.get(table_name)
        if table is None:
            continue
        if not columns:
            cleaned[table_name] = [c.name for c in table.columns]
        else:
            valid = [c for c in columns if c in {col.name for col in table.columns}]
            if valid:
                cleaned[table_name] = valid
    if not cleaned:
        raise ValueError("select at least one table and column")
    return {"tables": cleaned}
