from __future__ import annotations

import asyncio
from typing import Any

import duckdb

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.validators.duckdb_validator import DuckDBValidator


@CONNECTORS.register("duckdb_files")
class DuckDBFilesConnector(IDBConnector):
    """Query uploaded CSV/Parquet files via embedded DuckDB."""

    def __init__(self, *, connection: dict[str, Any]) -> None:
        self._files: dict[str, str] = dict(connection.get("files", {}))
        self._conn = duckdb.connect()
        for logical_name, path in self._files.items():
            if path.endswith(".csv"):
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW {logical_name} AS SELECT * FROM read_csv_auto('{path}')"
                )
            else:
                self._conn.execute(
                    f"CREATE OR REPLACE VIEW {logical_name} AS SELECT * FROM read_parquet('{path}')"
                )

    async def close(self) -> None:
        self._conn.close()

    async def test_connection(self) -> bool:
        return True

    async def introspect_schema(self) -> SchemaMetadata:
        tables: list[TableMeta] = []
        for logical_name, path in self._files.items():
            reader = "read_csv_auto" if path.endswith(".csv") else "read_parquet"

            def _describe(p: str, r: str) -> list:
                return self._conn.execute(f"DESCRIBE SELECT * FROM {r}('{p}')").fetchall()

            desc = await asyncio.to_thread(_describe, path, reader)
            columns = [ColumnMeta(name=row[0], data_type=row[1]) for row in desc]
            tables.append(TableMeta(name=logical_name, columns=columns))
        return SchemaMetadata(tables=tables)

    async def validate_sql(self, sql: str) -> ValidationResult:
        return await DuckDBValidator(conn=self._conn).validate(sql)

    async def execute_query(self, sql: str) -> QueryResult:
        result = await asyncio.to_thread(self._conn.execute, sql)
        if result.description is None:
            return QueryResult(columns=[], rows=[])
        cols = [d[0] for d in result.description]
        rows = result.fetchall()
        return QueryResult(columns=cols, rows=[list(r) for r in rows])
