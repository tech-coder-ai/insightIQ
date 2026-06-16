from __future__ import annotations

from typing import Any

from core.data.connectors.dbapi_base import DBAPIConnector
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta


@CONNECTORS.register("snowflake")
class SnowflakeConnector(DBAPIConnector):
    """Snowflake data warehouse via snowflake-connector-python."""

    def _connect(self) -> Any:
        try:
            import snowflake.connector as sf
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Snowflake driver not installed. Run: uv sync --extra connectors"
            ) from exc

        p = self._params
        kwargs: dict[str, Any] = {
            "account": p["account"],
            "user": p["user"],
            "password": p["password"],
            "warehouse": p["warehouse"],
            "database": p["database"],
            "login_timeout": 15,
        }
        if p.get("schema"):
            kwargs["schema"] = p["schema"]
        if p.get("role"):
            kwargs["role"] = p["role"]
        return sf.connect(**kwargs)

    def _introspect(self, conn: Any) -> SchemaMetadata:
        schema = self._params.get("schema")
        cur = conn.cursor()
        try:
            if schema:
                cur.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_schema = %s ORDER BY table_name",
                    (schema.upper(),),
                )
            else:
                cur.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('INFORMATION_SCHEMA') ORDER BY table_name"
                )
            table_rows = cur.fetchall()

            tables: list[TableMeta] = []
            for tbl_schema, table_name in table_rows:
                cur.execute(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
                    (tbl_schema, table_name),
                )
                columns = [
                    ColumnMeta(name=row[0], data_type=row[1], nullable=row[2] == "YES")
                    for row in cur.fetchall()
                ]
                tables.append(TableMeta(name=table_name, columns=columns))
            return SchemaMetadata(tables=tables)
        finally:
            cur.close()
