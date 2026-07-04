from __future__ import annotations

from typing import Any


def _clip_bbox_to_char_range(
    bbox: list[float],
    span_start: int,
    span_end: int,
    chunk_start: int,
    chunk_end: int,
) -> list[float] | None:
    overlap_start = max(span_start, chunk_start)
    overlap_end = min(span_end, chunk_end)
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


def _merge_boxes(boxes: list[list[float]], *, y_tol: float = 4.0, x_gap: float = 8.0) -> list[list[float]]:
    normalized = [list(box) for box in boxes if len(box) >= 4]
    if not normalized:
        return []
    normalized.sort(key=lambda box: (box[1], box[0]))
    merged: list[list[float]] = []
    for box in normalized:
        placed = False
        for idx, current in enumerate(merged):
            same_line = abs(current[1] - box[1]) <= y_tol and abs(current[3] - box[3]) <= y_tol
            adjacent = box[0] <= current[2] + x_gap and box[2] >= current[0] - x_gap
            if same_line and adjacent:
                merged[idx] = [
                    min(current[0], box[0]),
                    min(current[1], box[1]),
                    max(current[2], box[2]),
                    max(current[3], box[3]),
                ]
                placed = True
                break
        if not placed:
            merged.append(box)
    return merged


def _boxes_for_overlap(
    page_spans: list[dict[str, Any]],
    *,
    char_start: int,
    char_end: int,
) -> list[list[float]]:
    boxes: list[list[float]] = []
    for span in page_spans:
        bbox = span.get("bbox")
        if not bbox:
            continue
        clipped = _clip_bbox_to_char_range(
            bbox,
            int(span["char_start"]),
            int(span["char_end"]),
            char_start,
            char_end,
        )
        if clipped is not None:
            boxes.append(clipped)
    return _merge_boxes(boxes)


def assign_chunk_highlight_metadata(chunks: list[dict[str, Any]], text_spans: list[dict[str, Any]]) -> None:
    """Attach ``page_number``, ``bbox_json``, and ``highlight_regions`` to chunks."""
    if not text_spans:
        return
    for chunk in chunks:
        start = int(chunk["char_start"])
        end = int(chunk["char_end"])
        overlapping = [s for s in text_spans if int(s["char_end"]) > start and int(s["char_start"]) < end]
        if not overlapping:
            continue
        pages = sorted({int(s["page"]) for s in overlapping})
        chunk["page_number"] = pages[0]
        regions: list[dict[str, Any]] = []
        for page in pages:
            page_spans = [s for s in overlapping if int(s["page"]) == page]
            boxes = _boxes_for_overlap(page_spans, char_start=start, char_end=end)
            if not boxes:
                continue
            page_width = float(page_spans[0].get("page_width") or 0)
            page_height = float(page_spans[0].get("page_height") or 0)
            regions.append(
                {
                    "page": page,
                    "boxes": boxes,
                    "page_width": page_width,
                    "page_height": page_height,
                }
            )
        chunk["highlight_regions"] = regions
        if regions:
            primary = regions[0]
            chunk["bbox_json"] = {
                "page": primary["page"],
                "boxes": primary["boxes"],
                "page_width": primary["page_width"],
                "page_height": primary["page_height"],
            }


def regions_for_char_range(
    text_spans: list[dict[str, Any]],
    *,
    char_start: int,
    char_end: int,
) -> list[dict[str, Any]]:
    overlapping = [s for s in text_spans if int(s["char_end"]) > char_start and int(s["char_start"]) < char_end]
    if not overlapping:
        return []
    pages = sorted({int(s["page"]) for s in overlapping})
    regions: list[dict[str, Any]] = []
    for page in pages:
        page_spans = [s for s in overlapping if int(s["page"]) == page]
        boxes = _boxes_for_overlap(page_spans, char_start=char_start, char_end=char_end)
        if not boxes:
            continue
        regions.append(
            {
                "page": page,
                "boxes": boxes,
                "page_width": float(page_spans[0].get("page_width") or 0),
                "page_height": float(page_spans[0].get("page_height") or 0),
            }
        )
    return regions
