from __future__ import annotations

import asyncio
import json
from typing import Any

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.normalize import json_safe_row
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.data.validators.readonly import check_readonly_select


@CONNECTORS.register("bigquery")
class BigQueryConnector(IDBConnector):
    """Google BigQuery via the official google-cloud-bigquery client."""

    def __init__(self, *, connection: dict[str, Any]) -> None:
        self._params = connection
        self._project = connection["project"]
        self._dataset = connection["dataset"]
        self._client: Any | None = None

    def _build_client(self) -> Any:
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "BigQuery driver not installed. Run: uv sync --extra connectors"
            ) from exc

        raw = self._params.get("credentials_json")
        if raw:
            info = json.loads(raw) if isinstance(raw, str) else raw
            creds = service_account.Credentials.from_service_account_info(info)
            return bigquery.Client(project=self._project, credentials=creds)
        # Fall back to application default credentials (e.g. GCP workload identity).
        return bigquery.Client(project=self._project)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            client = self._client
            self._client = None
            await asyncio.to_thread(client.close)

    async def test_connection(self) -> bool:
        def _probe() -> bool:
            client = self._get_client()
            client.get_dataset(f"{self._project}.{self._dataset}")
            return True

        return await asyncio.to_thread(_probe)

    async def introspect_schema(self) -> SchemaMetadata:
        def _introspect() -> SchemaMetadata:
            client = self._get_client()
            dataset_ref = f"{self._project}.{self._dataset}"
            tables: list[TableMeta] = []
            for table_item in client.list_tables(dataset_ref):
                table = client.get_table(table_item.reference)
                columns = [
                    ColumnMeta(
                        name=field.name,
                        data_type=field.field_type,
                        nullable=field.mode != "REQUIRED",
                    )
                    for field in table.schema
                ]
                tables.append(TableMeta(name=table_item.table_id, columns=columns))
            return SchemaMetadata(tables=tables)

        return await asyncio.to_thread(_introspect)

    async def validate_sql(self, sql: str) -> ValidationResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            return guard

        def _dry_run() -> ValidationResult:
            from google.cloud import bigquery

            client = self._get_client()
            job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
            try:
                client.query(sql, job_config=job_config)
            except Exception as exc:  # noqa: BLE001 - surface planner errors
                return ValidationResult(ok=False, error=str(exc))
            return ValidationResult(ok=True)

        return await asyncio.to_thread(_dry_run)

    async def execute_query(self, sql: str) -> QueryResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            raise ValueError(guard.error or "destructive SQL is not allowed")

        def _run() -> QueryResult:
            client = self._get_client()
            result = client.query(sql).result()
            cols = [field.name for field in result.schema]
            rows = [[row[c] for c in cols] for row in result]
            return QueryResult(columns=cols, rows=[json_safe_row(row) for row in rows])

        return await asyncio.to_thread(_run)
