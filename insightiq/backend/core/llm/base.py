from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class ILLMProvider(ABC):
    @abstractmethod
    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str: ...
