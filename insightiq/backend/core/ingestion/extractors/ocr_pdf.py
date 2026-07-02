from __future__ import annotations

import asyncio
import logging

from core.ingestion.base import IExtractor
from core.ingestion.extractors.factory import EXTRACTORS


@EXTRACTORS.register("ocr_pdf")
class OcrPdfExtractor(IExtractor):
    """Extract text from PDFs, including scanned/image pages via OCR when available."""

    name = "ocr_pdf"

    async def extract(self, file_path: str) -> tuple[str, float]:
        return await asyncio.to_thread(_extract_pdf, file_path)


def _extract_pdf(file_path: str) -> tuple[str, float]:
    import pymupdf

    doc = pymupdf.open(file_path)
    parts: list[str] = []
    ocr_pages = 0
    try:
        for page in doc:
            text = (page.get_text() or "").strip()
            if len(text) < 20:
                ocr_text = _ocr_page(page)
                if ocr_text:
                    text = ocr_text
                    ocr_pages += 1
            if text:
                parts.append(text)
    finally:
        doc.close()

    combined = "\n\n".join(parts).strip()
    if not combined:
        return "", 0.2
    confidence = 0.82 if ocr_pages == 0 else 0.72
    if len(combined) < 50:
        confidence = min(confidence, 0.55)
    return combined, confidence


def _ocr_page(page: object) -> str:
    try:
        from PIL import Image
    except ImportError:
        return ""

    try:
        pix = page.get_pixmap(dpi=200)  # type: ignore[attr-defined]
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    except Exception:  # noqa: BLE001 - OCR is best-effort
        return ""

    # Prefer RapidOCR: pure-pip, models ship inside the wheel, no system binary needed.
    # Falls back to pytesseract for anyone who already has the Tesseract engine installed.
    text = _ocr_with_rapidocr(img)
    if text:
        return text
    return _ocr_with_pytesseract(img)


_rapidocr_engine: object | None = None


def _get_rapidocr_engine() -> object:
    global _rapidocr_engine
    if _rapidocr_engine is None:
        from rapidocr import RapidOCR

        _rapidocr_engine = RapidOCR()
        # Silence RapidOCR's INFO-level "Using engine_name: ..." chatter on future calls.
        # `setLevel()` gets reset internally by the library, but `disabled` is never touched.
        logging.getLogger("RapidOCR").disabled = True
    return _rapidocr_engine


def _ocr_with_rapidocr(img: object) -> str:
    try:
        import numpy as np
    except ImportError:
        return ""

    try:
        engine = _get_rapidocr_engine()
        result = engine(np.array(img))
        txts = getattr(result, "txts", None) or ()
        return "\n".join(t for t in txts if t).strip()
    except Exception:  # noqa: BLE001 - RapidOCR not installed, or OCR failed on this page
        return ""


def _ocr_with_pytesseract(img: object) -> str:
    try:
        import pytesseract
    except ImportError:
        return ""

    try:
        return (pytesseract.image_to_string(img) or "").strip()
    except Exception:  # noqa: BLE001 - system tesseract binary not installed
        return ""
