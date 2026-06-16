from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.validators.base import ISQLValidator, ValidationResult
from core.data.validators.factory import VALIDATORS


DESTRUCTIVE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|MERGE|CALL|ALTER|GRANT|REVOKE|CREATE)\b",
    re.IGNORECASE,
)


@VALIDATORS.register("postgres")
class PostgresValidator(ISQLValidator):
    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def validate(self, sql: str) -> ValidationResult:
        if DESTRUCTIVE.search(sql):
            return ValidationResult(ok=False, error="destructive SQL is not allowed")
        try:
            await self._session.execute(text(f"EXPLAIN {sql}"))
        except Exception as e:
            return ValidationResult(ok=False, error=str(e))
        return ValidationResult(ok=True)

