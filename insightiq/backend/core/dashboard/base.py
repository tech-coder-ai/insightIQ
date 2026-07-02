from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from core.registry import Registry


class RefreshResult(BaseModel):
    response: dict[str, Any]


class ICardRefresher(ABC):
    @abstractmethod
    async def refresh(
        self,
        *,
        source_config: dict[str, Any],
        tenant_id: str,
        filters: dict[str, Any] | None = None,
    ) -> RefreshResult: ...


CARD_REFRESHERS: Registry[ICardRefresher] = Registry("card_refresher")
