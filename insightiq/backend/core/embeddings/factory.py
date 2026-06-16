from __future__ import annotations

import importlib

from core.embeddings.base import IEmbedder
from core.registry import Registry

EMBEDDERS: Registry[IEmbedder] = Registry("embedder")


class EmbedderFactory:
    @staticmethod
    def create(key: str, **kw: object) -> IEmbedder:
        try:
            importlib.import_module("core.embeddings.hash_dev")
        except ModuleNotFoundError:
            pass
        return EMBEDDERS.create(key, **kw)
