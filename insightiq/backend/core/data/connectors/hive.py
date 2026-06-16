from __future__ import annotations

from typing import Any

from core.data.connectors.dbapi_base import DBAPIConnector
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta


@CONNECTORS.register("hive")
class HiveConnector(DBAPIConnector):
    """Apache Hive (HiveServer2) via PyHive over Thrift."""

    def _connect(self) -> Any:
        try:
            from pyhive import hive
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Hive driver not installed. Run: uv sync --extra connectors"
            ) from exc

        p = self._params
        auth = str(p.get("auth", "NOSASL")).upper()
        kwargs: dict[str, Any] = {
            "host": p.get("host", "localhost"),
            "port": int(p.get("port", 10000)),
            "database": p.get("database", "default"),
            "auth": auth,
        }
        if p.get("user"):
            kwargs["username"] = p["user"]
        if auth in {"LDAP", "CUSTOM"} and p.get("password"):
            kwargs["password"] = p["password"]
        if auth == "KERBEROS":
            kwargs["kerberos_service_name"] = p.get("kerberos_service_name", "hive")
        return hive.Connection(**kwargs)

    def _introspect(self, conn: Any) -> SchemaMetadata:
        cur = conn.cursor()
        try:
            cur.execute("SHOW TABLES")
            table_names = [row[0] for row in cur.fetchall()]

            tables: list[TableMeta] = []
            for table_name in table_names:
                cur.execute(f"DESCRIBE {table_name}")
                columns: list[ColumnMeta] = []
                for row in cur.fetchall():
                    col_name = (row[0] or "").strip()
                    # DESCRIBE output ends with blank lines / partition metadata.
                    if not col_name or col_name.startswith("#"):
                        break
                    columns.append(ColumnMeta(name=col_name, data_type=(row[1] or "").strip()))
                tables.append(TableMeta(name=table_name, columns=columns))
            return SchemaMetadata(tables=tables)
        finally:
            cur.close()
