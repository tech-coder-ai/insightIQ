from __future__ import annotations

import importlib

from core.ingestion.extractors.factory import EXTRACTORS


def route_extraction(file_path: str) -> str:
    """MarkItDown first; escalate to docling/unstructured by extension/heuristics."""
    lower = file_path.lower()
    if lower.endswith((".pdf", ".docx", ".pptx")):
        return "markitdown"
    return "markitdown"


async def extract_document(file_path: str) -> tuple[str, str, float]:
    key = route_extraction(file_path)
    try:
        importlib.import_module("core.ingestion.extractors.markitdown")
    except ModuleNotFoundError:
        pass
    extractor = EXTRACTORS.create(key)
    text, confidence = await extractor.extract(file_path)
    if confidence < 0.6:
        extractor = EXTRACTORS.create("docling")
        text, confidence = await extractor.extract(file_path)
    if confidence < 0.55:
        extractor = EXTRACTORS.create("unstructured")
        text, confidence = await extractor.extract(file_path)
    return text, extractor.name, confidence
