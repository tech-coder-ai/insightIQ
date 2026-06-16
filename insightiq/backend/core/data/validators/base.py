from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ValidationResult(BaseModel):
    ok: bool
    error: str | None = None


class ISQLValidator(ABC):
    @abstractmethod
    async def validate(self, sql: str) -> ValidationResult: ...

