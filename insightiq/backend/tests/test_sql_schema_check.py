from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.sql_schema_check import validate_sql_against_schema


def test_validate_sql_rejects_unknown_table():
    schema = SchemaMetadata(
        tables=[TableMeta(name="orders", columns=[ColumnMeta(name="amount", data_type="numeric")])]
    )
    result = validate_sql_against_schema("SELECT amount FROM customers", schema)
    assert not result.ok
    assert "customers" in (result.error or "")


def test_validate_sql_accepts_qualified_columns():
    schema = SchemaMetadata(
        tables=[
            TableMeta(
                name="orders",
                columns=[
                    ColumnMeta(name="order_date", data_type="date"),
                    ColumnMeta(name="amount", data_type="numeric"),
                ],
            )
        ]
    )
    sql = (
        "SELECT DATE_TRUNC('month', o.order_date) AS month, SUM(o.amount) AS total "
        "FROM orders o GROUP BY 1 ORDER BY 1"
    )
    result = validate_sql_against_schema(sql, schema)
    assert result.ok
