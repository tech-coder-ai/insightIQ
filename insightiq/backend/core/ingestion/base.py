from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IChunker(ABC):
    @abstractmethod
    def chunk(self, text: str, *, document_id: str) -> list[dict[str, Any]]: ...


class IExtractor(ABC):
    name: str

    @abstractmethod
    async def extract(self, file_path: str) -> tuple[str, float]:
        """Return (markdown, confidence 0-1)."""
