from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher, RefreshResult
from core.data.runner import open_connector
from core.deps import get_app_sessionmaker
from core.models import DataSource
from core.response.classifier import classify_and_format
from core.response.formatter import format_data_table


@CARD_REFRESHERS.register("sql")
class SqlCardRefresher(ICardRefresher):
    async def refresh(self, *, source_config: dict[str, Any], tenant_id: str) -> RefreshResult:
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

        question = source_config.get("question", "")
        payload = classify_and_format(result, question=question) if question else format_data_table(result)
        return RefreshResult(response=payload.model_dump())
