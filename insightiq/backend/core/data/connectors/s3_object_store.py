from __future__ import annotations

import asyncio
from typing import Any

import duckdb

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.normalize import json_safe_row
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.validators.duckdb_validator import DuckDBValidator
from core.data.validators.readonly import check_readonly_select


def _configure_s3(conn: duckdb.DuckDBPyConnection, connection: dict[str, Any]) -> None:
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    endpoint = connection.get("endpoint", "localhost:9000")
    region = connection.get("region", "us-east-1")
    access_key = connection["access_key"]
    secret_key = connection["secret_key"]
    url_style = connection.get("url_style", "path")
    conn.execute(
        f"""
        CREATE OR REPLACE SECRET insightiq_s3 (
            TYPE S3,
            KEY_ID '{access_key}',
            SECRET '{secret_key}',
            ENDPOINT '{endpoint}',
            REGION '{region}',
            URL_STYLE '{url_style}'
        );
        """
    )


def _read_fn(glob: str) -> str:
    if glob.endswith(".csv") or "*.csv" in glob:
        return f"read_csv_auto('{glob}')"
    return f"read_parquet('{glob}')"


@CONNECTORS.register("s3_object_store")
class S3ObjectStoreConnector(IDBConnector):
    """Query S3/MinIO files via embedded DuckDB — no cluster required."""

    def __init__(self, *, connection: dict[str, Any]) -> None:
        self._connection = connection
        self._globs: dict[str, str] = dict(connection.get("table_globs", {}))
        self._conn = duckdb.connect()
        _configure_s3(self._conn, connection)
        self._create_views()

    def _create_views(self) -> None:
        for logical_name, glob in self._globs.items():
            reader = _read_fn(glob)
            self._conn.execute(f"CREATE OR REPLACE VIEW {logical_name} AS SELECT * FROM {reader}")

    async def close(self) -> None:
        self._conn.close()

    async def test_connection(self) -> bool:
        if not self._globs:
            return True
        first_glob = next(iter(self._globs.values()))

        def _probe() -> None:
            self._conn.execute(f"SELECT 1 FROM {_read_fn(first_glob)} LIMIT 1")

        await asyncio.to_thread(_probe)
        return True

    async def introspect_schema(self) -> SchemaMetadata:
        tables: list[TableMeta] = []
        for logical_name, glob in self._globs.items():

            def _describe(g: str) -> list:
                return self._conn.execute(f"DESCRIBE SELECT * FROM {_read_fn(g)}").fetchall()

            desc = await asyncio.to_thread(_describe, glob)
            columns = [ColumnMeta(name=row[0], data_type=row[1]) for row in desc]
            tables.append(TableMeta(name=logical_name, columns=columns))
        return SchemaMetadata(tables=tables)

    async def validate_sql(self, sql: str) -> ValidationResult:
        validator = DuckDBValidator(conn=self._conn)
        return await validator.validate(sql)

    async def execute_query(self, sql: str) -> QueryResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            raise ValueError(guard.error or "destructive SQL is not allowed")
        result = await asyncio.to_thread(self._conn.execute, sql)
        if result.description is None:
            return QueryResult(columns=[], rows=[])
        cols = [d[0] for d in result.description]
        rows = result.fetchall()
        return QueryResult(columns=cols, rows=[json_safe_row(list(r)) for r in rows])
