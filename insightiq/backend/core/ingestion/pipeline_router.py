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
    lower = file_path.lower()
    try:
        importlib.import_module("core.ingestion.extractors.markitdown")
        importlib.import_module("core.ingestion.extractors.ocr_pdf")
    except ModuleNotFoundError:
        pass
    extractor = EXTRACTORS.create(key)
    text, confidence = await extractor.extract(file_path)
    if lower.endswith(".pdf") and (confidence < 0.6 or len(text.strip()) < 40):
        try:
            ocr_extractor = EXTRACTORS.create("ocr_pdf")
            ocr_text, ocr_confidence = await ocr_extractor.extract(file_path)
            if len(ocr_text.strip()) > len(text.strip()):
                text, confidence = ocr_text, ocr_confidence
                extractor = ocr_extractor
        except KeyError:
            pass
    if confidence < 0.6:
        extractor = EXTRACTORS.create("docling")
        text, confidence = await extractor.extract(file_path)
    if confidence < 0.55:
        extractor = EXTRACTORS.create("unstructured")
        text, confidence = await extractor.extract(file_path)
    return text, extractor.name, confidence
