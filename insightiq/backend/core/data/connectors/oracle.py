from __future__ import annotations

from typing import Any

from core.data.connectors.dbapi_base import DBAPIConnector
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta


@CONNECTORS.register("oracle")
class OracleConnector(DBAPIConnector):
    """Oracle Database via python-oracledb in thin mode (no Oracle client needed)."""

    TEST_SQL = "SELECT 1 FROM DUAL"

    def _connect(self) -> Any:
        try:
            import oracledb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Oracle driver not installed. Run: uv sync --extra connectors"
            ) from exc

        p = self._params
        host = p.get("host", "localhost")
        port = p.get("port", 1521)
        service = p["database"]  # service name
        dsn = oracledb.makedsn(host, port, service_name=service)
        return oracledb.connect(user=p["user"], password=p["password"], dsn=dsn)

    def _introspect(self, conn: Any) -> SchemaMetadata:
        cur = conn.cursor()
        try:
            cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            table_names = [row[0] for row in cur.fetchall()]

            tables: list[TableMeta] = []
            for table_name in table_names:
                cur.execute(
                    "SELECT column_name, data_type, nullable FROM user_tab_columns "
                    "WHERE table_name = :tbl ORDER BY column_id",
                    {"tbl": table_name},
                )
                columns = [
                    ColumnMeta(name=row[0], data_type=row[1], nullable=row[2] == "Y")
                    for row in cur.fetchall()
                ]
                tables.append(TableMeta(name=table_name, columns=columns))
            return SchemaMetadata(tables=tables)
        finally:
            cur.close()
