from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResponseType(StrEnum):
    data_table = "data_table"
    explanation = "explanation"
    error = "error"


class ResponsePayload(BaseModel):
    response_type: ResponseType
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
