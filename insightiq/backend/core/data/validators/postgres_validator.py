from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.validators.base import ISQLValidator, ValidationResult
from core.data.validators.factory import VALIDATORS
from core.data.validators.readonly import check_readonly_select


@VALIDATORS.register("postgres")
class PostgresValidator(ISQLValidator):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def validate(self, sql: str) -> ValidationResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            return guard
        try:
            await self._session.execute(text(f"EXPLAIN {sql}"))
        except Exception as e:
            return ValidationResult(ok=False, error=str(e))
        return ValidationResult(ok=True)

