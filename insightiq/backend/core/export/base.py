from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from core.registry import Registry


class ExportPayload(BaseModel):
    title: str
    content_type: str  # conversation | dashboard
    data: dict[str, Any] = Field(default_factory=dict)


class ExportResult(BaseModel):
    filename: str
    media_type: str
    data: bytes


class IExporter(ABC):
    @abstractmethod
    async def export(self, *, payload: ExportPayload) -> ExportResult: ...


EXPORTERS: Registry[IExporter] = Registry("exporter")
