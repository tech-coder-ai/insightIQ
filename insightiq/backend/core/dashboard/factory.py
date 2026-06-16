from __future__ import annotations

import importlib

from core.dashboard.base import ICardRefresher
from core.dashboard.base import CARD_REFRESHERS


class CardRefresherFactory:
    @staticmethod
    def create(source_type: str) -> ICardRefresher:
        for module in ("core.dashboard.refreshers.sql", "core.dashboard.refreshers.rag"):
            try:
                importlib.import_module(module)
            except ModuleNotFoundError:
                pass
        return CARD_REFRESHERS.create(source_type)
