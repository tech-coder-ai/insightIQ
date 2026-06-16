from __future__ import annotations

import importlib

from core.registry import Registry
from core.data.connectors.base import IDBConnector


CONNECTORS: Registry[IDBConnector] = Registry("connector")


class ConnectorFactory:
    @staticmethod
    def create(db_type: str, **kw: object) -> IDBConnector:
        # Auto-import by convention to avoid needing to edit a central file for new connectors.
        # Adding a new source is just: create `core/data/connectors/<db_type>.py` with registry decoration.
        try:
            importlib.import_module(f"core.data.connectors.{db_type}")
        except ModuleNotFoundError:
            pass
        return CONNECTORS.create(db_type, **kw)

