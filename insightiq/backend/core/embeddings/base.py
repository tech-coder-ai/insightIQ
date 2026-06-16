from __future__ import annotations

from abc import ABC, abstractmethod


class IEmbedder(ABC):
    model_name: str
    dimension: int

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
