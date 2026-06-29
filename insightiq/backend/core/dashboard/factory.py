from __future__ import annotations

import importlib

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher


class CardRefresherFactory:
    @staticmethod
    def create(source_type: str) -> ICardRefresher:
        for module in (
            "core.dashboard.refreshers.sql",
            "core.dashboard.refreshers.rag",
            "core.dashboard.refreshers.prompt",
        ):
            try:
                importlib.import_module(module)
            except ModuleNotFoundError:
                pass
        return CARD_REFRESHERS.create(source_type)
