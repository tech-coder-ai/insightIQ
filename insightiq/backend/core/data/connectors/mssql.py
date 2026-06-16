from __future__ import annotations

from typing import Any

from core.data.connectors.dbapi_base import DBAPIConnector
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta


@CONNECTORS.register("mssql")
class MSSQLConnector(DBAPIConnector):
    """Microsoft SQL Server / Azure SQL via pymssql (FreeTDS, no ODBC required)."""

    def _connect(self) -> Any:
        try:
            import pymssql
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "SQL Server driver not installed. Run: uv sync --extra connectors"
            ) from exc

        p = self._params
        return pymssql.connect(
            server=p.get("host", "localhost"),
            port=str(p.get("port", 1433)),
            user=p["user"],
            password=p["password"],
            database=p["database"],
            login_timeout=10,
            timeout=30,
        )

    def _introspect(self, conn: Any) -> SchemaMetadata:
        schema = self._params.get("schema")
        cur = conn.cursor()
        try:
            if schema:
                cur.execute(
                    "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = %s "
                    "ORDER BY TABLE_NAME",
                    (schema,),
                )
            else:
                cur.execute(
                    "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
                )
            table_rows = cur.fetchall()

            tables: list[TableMeta] = []
            for tbl_schema, table_name in table_rows:
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                    (tbl_schema, table_name),
                )
                columns = [
                    ColumnMeta(name=row[0], data_type=row[1], nullable=row[2] == "YES")
                    for row in cur.fetchall()
                ]
                # Qualify non-dbo tables so generated SQL can reference them.
                name = table_name if tbl_schema == "dbo" else f"{tbl_schema}.{table_name}"
                tables.append(TableMeta(name=name, columns=columns))
            return SchemaMetadata(tables=tables)
        finally:
            cur.close()
