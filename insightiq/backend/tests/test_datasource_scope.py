from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.scope import apply_selected_scope, default_scope_from_schema, scope_to_storage


def test_default_scope_from_schema():
    schema = SchemaMetadata(
        tables=[
            TableMeta(name="customers", columns=[ColumnMeta(name="id", data_type="int")]),
            TableMeta(name="orders", columns=[ColumnMeta(name="total", data_type="numeric")]),
        ]
    )
    scope = default_scope_from_schema(schema)
    assert scope == {"tables": {"customers": ["id"], "orders": ["total"]}}


def test_apply_selected_scope_filters_tables_and_columns():
    schema = SchemaMetadata(
        tables=[
            TableMeta(
                name="customers",
                columns=[
                    ColumnMeta(name="id", data_type="int"),
                    ColumnMeta(name="email", data_type="text"),
                ],
            ),
            TableMeta(name="orders", columns=[ColumnMeta(name="total", data_type="numeric")]),
        ]
    )
    scoped = apply_selected_scope(schema, {"tables": {"customers": ["id"]}})
    assert [t.name for t in scoped.tables] == ["customers"]
    assert [c.name for c in scoped.tables[0].columns] == ["id"]


def test_scope_to_storage_requires_valid_selection():
    schema = SchemaMetadata(
        tables=[TableMeta(name="customers", columns=[ColumnMeta(name="id", data_type="int")])]
    )
    stored = scope_to_storage({"tables": {"customers": ["id"]}}, schema)
    assert stored == {"tables": {"customers": ["id"]}}
