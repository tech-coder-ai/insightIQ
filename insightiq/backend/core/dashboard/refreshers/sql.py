from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher, RefreshResult
from core.data.connectors.base import QueryResult
from core.data.runner import open_connector
from core.deps import get_app_sessionmaker
from core.models import DataSource
from core.response.classifier import classify_and_format
from core.response.formatter import format_data_table


def _apply_filters(result: QueryResult, filters: dict[str, Any] | None) -> QueryResult:
    """Best-effort client-side filtering of a query result using dashboard global filters.

    Filters are matched against the result's own column names so this works for any
    query shape without needing to rewrite arbitrary SQL.
    """
    if not filters:
        return result
    col_index = {c.lower(): i for i, c in enumerate(result.columns)}
    rows = result.rows

    region = filters.get("region")
    if region and "region" in col_index:
        idx = col_index["region"]
        needle = str(region).strip().lower()
        rows = [r for r in rows if str(r[idx]).strip().lower() == needle]

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from or date_to:
        date_idx = next((i for c, i in col_index.items() if "date" in c), None)
        if date_idx is not None:

            def _in_range(value: Any) -> bool:
                text = str(value)[:10]
                if date_from and text < str(date_from):
                    return False
                if date_to and text > str(date_to):
                    return False
                return True

            rows = [r for r in rows if _in_range(r[date_idx])]

    return QueryResult(columns=result.columns, rows=rows)


@CARD_REFRESHERS.register("sql")
class SqlCardRefresher(ICardRefresher):
    async def refresh(
        self,
        *,
        source_config: dict[str, Any],
        tenant_id: str,
        filters: dict[str, Any] | None = None,
    ) -> RefreshResult:
        datasource_id = uuid.UUID(source_config["datasource_id"])
        sql = source_config["sql"]
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as db:
            res = await db.execute(
                select(DataSource).where(
                    DataSource.id == datasource_id,
                    DataSource.tenant_id == uuid.UUID(tenant_id),
                )
            )
            ds = res.scalar_one_or_none()
            if ds is None:
                raise ValueError("datasource not found")

        async with open_connector(ds.db_type, ds.connection_config_json) as connector:
            validation = await connector.validate_sql(sql)
            if not validation.ok:
                raise ValueError(validation.error or "invalid SQL")
            result = await connector.execute_query(sql)

        result = _apply_filters(result, filters)
        question = source_config.get("question", "")
        payload = classify_and_format(result, question=question) if question else format_data_table(result)
        return RefreshResult(response=payload.model_dump())
