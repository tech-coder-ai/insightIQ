from __future__ import annotations

from core.ingestion.base import IChunker
from core.registry import Registry

CHUNKERS: Registry[IChunker] = Registry("chunker")
