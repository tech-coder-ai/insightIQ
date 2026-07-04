from __future__ import annotations

from typing import Any


def extract_pdf_structured(file_path: str) -> tuple[str, list[dict[str, Any]], int, float]:
    """Extract PDF text with per-span bounding boxes for source highlighting.

    Returns ``(markdown, text_spans, page_count, confidence)`` where each span is:
    ``{char_start, char_end, page, bbox, page_width, page_height, text}``.
    """
    import pymupdf

    doc = pymupdf.open(file_path)
    parts: list[str] = []
    spans: list[dict[str, Any]] = []
    offset = 0
    ocr_pages = 0

    try:
        for page_index, page in enumerate(doc, start=1):
            if page_index > 1:
                marker = f"\n\n<!-- page:{page_index} -->\n\n"
                parts.append(marker)
                offset += len(marker)

            page_dict = page.get_text("dict")
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            page_lines: list[str] = []

            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    raw_parts = [str(span.get("text", "")) for span in line.get("spans", [])]
                    joined = "".join(raw_parts)
                    line_text = joined.strip()
                    if not line_text:
                        continue
                    line_start = offset + sum(len(x) + 1 for x in page_lines) if page_lines else offset
                    leading = len(joined) - len(joined.lstrip())
                    trailing = len(joined) - len(joined.rstrip())
                    visible_start = line_start + leading
                    visible_end = line_start + len(joined) - trailing
                    cursor = line_start
                    for span in line.get("spans", []):
                        text = str(span.get("text", ""))
                        if not text:
                            continue
                        span_start = cursor
                        span_end = cursor + len(text)
                        cursor = span_end
                        bbox = span.get("bbox")
                        if not bbox:
                            continue
                        overlap_start = max(span_start, visible_start)
                        overlap_end = min(span_end, visible_end)
                        if overlap_end <= overlap_start:
                            continue
                        clipped = _clip_bbox_to_char_range(bbox, span_start, span_end, overlap_start, overlap_end)
                        if clipped is None:
                            continue
                        spans.append(
                            {
                                "char_start": overlap_start,
                                "char_end": overlap_end,
                                "page": page_index,
                                "bbox": clipped,
                                "page_width": page_width,
                                "page_height": page_height,
                                "text": joined[overlap_start - line_start : overlap_end - line_start],
                            }
                        )
                    page_lines.append(line_text)

            page_text = "\n".join(page_lines).strip()
            if len(page_text) < 20:
                ocr_text, ocr_spans, ocr_offset = _ocr_page_with_boxes(page, page_index, offset, page_width, page_height)
                if ocr_text:
                    page_text = ocr_text
                    spans.extend(ocr_spans)
                    ocr_pages += 1

            if page_text:
                parts.append(page_text)
                offset += len(page_text)
    finally:
        page_count = doc.page_count
        doc.close()

    markdown = "\n\n".join(p.strip() for p in parts if p.strip()).strip()
    if not markdown:
        return "", [], page_count, 0.2
    confidence = 0.82 if ocr_pages == 0 else 0.72
    if len(markdown) < 50:
        confidence = min(confidence, 0.55)
    return markdown, spans, page_count, confidence


def _union_span_boxes(spans: list[dict[str, Any]]) -> list[float] | None:
    boxes = [span.get("bbox") for span in spans if span.get("bbox")]
    if not boxes:
        return None
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return [float(x0), float(y0), float(x1), float(y1)]


def _clip_bbox_to_char_range(
    bbox: list[float] | tuple[float, ...],
    span_start: int,
    span_end: int,
    overlap_start: int,
    overlap_end: int,
) -> list[float] | None:
    if overlap_end <= overlap_start:
        return None
    if overlap_start <= span_start and overlap_end >= span_end:
        return [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
    span_len = max(span_end - span_start, 1)
    x0, y0, x1, y1 = bbox
    width = x1 - x0
    left_ratio = (overlap_start - span_start) / span_len
    right_ratio = (overlap_end - span_start) / span_len
    return [float(x0 + width * left_ratio), float(y0), float(x0 + width * right_ratio), float(y1)]


def _ocr_page_with_boxes(
    page: object,
    page_index: int,
    offset: int,
    page_width: float,
    page_height: float,
) -> tuple[str, list[dict[str, Any]], int]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", [], offset

    try:
        pix = page.get_pixmap(dpi=200)  # type: ignore[attr-defined]
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:  # noqa: BLE001
        return "", [], offset

    lines: dict[tuple[int, int, int], list[str]] = {}
    line_boxes: dict[tuple[int, int, int], list[list[float]]] = {}
    for i, word in enumerate(data.get("text", [])):
        word = (word or "").strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        scale_x = page_width / float(pix.width)
        scale_y = page_height / float(pix.height)
        line_boxes.setdefault(key, []).append([x * scale_x, y * scale_y, (x + w) * scale_x, (y + h) * scale_y])

    page_lines: list[str] = []
    span_rows: list[dict[str, Any]] = []
    cursor = offset
    for key in sorted(lines.keys()):
        line_text = " ".join(lines[key]).strip()
        if not line_text:
            continue
        if page_lines:
            cursor += 1
        line_start = cursor
        line_end = line_start + len(line_text)
        boxes = line_boxes.get(key, [])
        union = _union_boxes(boxes)
        if union:
            span_rows.append(
                {
                    "char_start": line_start,
                    "char_end": line_end,
                    "page": page_index,
                    "bbox": union,
                    "page_width": page_width,
                    "page_height": page_height,
                    "text": line_text,
                }
            )
        page_lines.append(line_text)
        cursor = line_end

    return "\n".join(page_lines).strip(), span_rows, cursor


def _union_boxes(boxes: list[list[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]
