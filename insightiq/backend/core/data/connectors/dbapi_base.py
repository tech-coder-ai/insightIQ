from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.normalize import json_safe_row
from core.data.schema import SchemaMetadata
from core.data.validators.readonly import check_readonly_select


class DBAPIConnector(IDBConnector):
    """Base for synchronous PEP-249 (DB-API 2.0) drivers.

    Subclasses implement ``_connect`` (open a driver connection) and
    ``_introspect`` (build schema metadata from a live connection). All blocking
    driver work is dispatched to a worker thread so the event loop stays free.
    """

    #: Lightweight liveness probe; override per dialect (e.g. Oracle needs DUAL).
    TEST_SQL = "SELECT 1"

    def __init__(self, *, connection: dict[str, Any]) -> None:
        self._params = connection
        self._conn: Any | None = None

    @abstractmethod
    def _connect(self) -> Any:
        """Open and return a DB-API connection. Runs in a worker thread."""

    @abstractmethod
    def _introspect(self, conn: Any) -> SchemaMetadata:
        """Build schema metadata from an open connection. Runs in a worker thread."""

    def _get_conn(self) -> Any:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    async def close(self) -> None:
        if self._conn is not None:
            conn = self._conn
            self._conn = None
            await asyncio.to_thread(conn.close)

    async def test_connection(self) -> bool:
        def _probe() -> bool:
            cur = self._get_conn().cursor()
            try:
                cur.execute(self.TEST_SQL)
                cur.fetchall()
            finally:
                cur.close()
            return True

        return await asyncio.to_thread(_probe)

    async def introspect_schema(self) -> SchemaMetadata:
        return await asyncio.to_thread(lambda: self._introspect(self._get_conn()))

    async def validate_sql(self, sql: str) -> ValidationResult:
        return check_readonly_select(sql)

    async def execute_query(self, sql: str) -> QueryResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            raise ValueError(guard.error or "destructive SQL is not allowed")

        def _run() -> QueryResult:
            cur = self._get_conn().cursor()
            try:
                cur.execute(sql)
                if cur.description is None:
                    return QueryResult(columns=[], rows=[])
                cols = [str(d[0]) for d in cur.description]
                rows = cur.fetchall()
                return QueryResult(columns=cols, rows=[json_safe_row(list(r)) for r in rows])
            finally:
                cur.close()

        return await asyncio.to_thread(_run)
