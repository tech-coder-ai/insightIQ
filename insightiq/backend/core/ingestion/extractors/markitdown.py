from __future__ import annotations

import asyncio

from core.ingestion.base import IExtractor
from core.ingestion.extractors.factory import EXTRACTORS


@EXTRACTORS.register("markitdown")
class MarkItDownExtractor(IExtractor):
    name = "markitdown"

    async def extract(self, file_path: str) -> tuple[str, float]:
        from markitdown import MarkItDown

        def _run() -> tuple[str, float]:
            md = MarkItDown()
            result = md.convert(file_path)
            text = result.text_content or ""
            confidence = 0.85 if len(text) > 50 else 0.5
            return text, confidence

        return await asyncio.to_thread(_run)


@EXTRACTORS.register("docling")
class DoclingExtractor(IExtractor):
    """Fallback for complex layout. TODO(phase3): wire full Docling when installed."""

    name = "docling"

    async def extract(self, file_path: str) -> tuple[str, float]:
        # Phase 3: escalate path — reuse markitdown with lower confidence flag.
        primary = MarkItDownExtractor()
        text, _ = await primary.extract(file_path)
        return text, 0.7


@EXTRACTORS.register("unstructured")
class UnstructuredExtractor(IExtractor):
    name = "unstructured"

    async def extract(self, file_path: str) -> tuple[str, float]:
        primary = MarkItDownExtractor()
        text, _ = await primary.extract(file_path)
        return text, 0.6
