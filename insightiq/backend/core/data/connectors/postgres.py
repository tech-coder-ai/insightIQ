from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.connectors.base import IDBConnector, QueryResult, ValidationResult
from core.data.connectors.factory import CONNECTORS
from core.data.validators.factory import ValidatorFactory


@CONNECTORS.register("postgres")
class PostgresConnector(IDBConnector):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def test_connection(self) -> bool:
        await self._session.execute(text("SELECT 1"))
        return True

    async def validate_sql(self, sql: str) -> ValidationResult:
        validator = ValidatorFactory.create("postgres", session=self._session)
        res = await validator.validate(sql)
        return ValidationResult(ok=res.ok, error=res.error)

    async def execute_query(self, sql: str) -> QueryResult:
        result = await self._session.execute(text(sql))
        rows = result.fetchall()
        cols = list(result.keys())
        return QueryResult(columns=cols, rows=[list(r) for r in rows])

