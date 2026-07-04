from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from core.ingestion.extractors.factory import EXTRACTORS


@dataclass
class ExtractionResult:
    markdown: str
    extractor_used: str
    confidence: float
    text_spans: list[dict[str, Any]] = field(default_factory=list)
    page_count: int | None = None


def route_extraction(file_path: str) -> str:
    """MarkItDown first; escalate to docling/unstructured by extension/heuristics."""
    lower = file_path.lower()
    if lower.endswith((".pdf", ".docx", ".pptx")):
        return "markitdown"
    return "markitdown"


async def extract_document(file_path: str) -> ExtractionResult:
    lower = file_path.lower()
    if lower.endswith(".pdf"):
        try:
            from core.ingestion.extractors.pdf_structured import extract_pdf_structured

            markdown, spans, page_count, confidence = extract_pdf_structured(file_path)
            if markdown.strip():
                return ExtractionResult(
                    markdown=markdown,
                    extractor_used="pdf_structured",
                    confidence=confidence,
                    text_spans=spans,
                    page_count=page_count,
                )
        except Exception:  # noqa: BLE001 - fall back to generic extractors
            pass

    key = route_extraction(file_path)
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
    return ExtractionResult(markdown=text, extractor_used=extractor.name, confidence=confidence)
