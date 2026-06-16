from __future__ import annotations

import duckdb

from core.data.validators.base import ISQLValidator, ValidationResult
from core.data.validators.factory import VALIDATORS
from core.data.validators.readonly import check_readonly_select


@VALIDATORS.register("duckdb")
class DuckDBValidator(ISQLValidator):
    def __init__(self, *, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn

    async def validate(self, sql: str) -> ValidationResult:
        guard = check_readonly_select(sql)
        if not guard.ok:
            return guard
        try:
            self._conn.execute(f"EXPLAIN {sql}")
        except Exception as e:
            return ValidationResult(ok=False, error=str(e))
        return ValidationResult(ok=True)
