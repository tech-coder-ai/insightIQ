from __future__ import annotations

from core.ingestion.base import IExtractor
from core.registry import Registry

EXTRACTORS: Registry[IExtractor] = Registry("extractor")
