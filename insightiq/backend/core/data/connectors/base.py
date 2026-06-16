from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class DataSourceConfig(BaseModel):
    tenant_id: str
    db_type: str
    connection: dict[str, Any]


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]


class ValidationResult(BaseModel):
    ok: bool
    error: str | None = None


class IDBConnector(ABC):
    @abstractmethod
    async def test_connection(self) -> bool: ...

    @abstractmethod
    async def execute_query(self, sql: str) -> QueryResult: ...

    @abstractmethod
    async def validate_sql(self, sql: str) -> ValidationResult: ...

