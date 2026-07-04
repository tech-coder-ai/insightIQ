from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.ingestion.base import IChunker
from core.ingestion.chunkers.factory import CHUNKERS

_HEADER_RE = re.compile(r"^#{1,6}\s+\S.*$", re.MULTILINE)
_FENCE_RE = re.compile(r"^```", re.MULTILINE)
_BLANK_LINE_RE = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class _Span:
    start: int
    end: int


def _find_sections(text: str) -> list[_Span]:
    """Split text into sections at Markdown headers (principle 1 — layout-aware
    parsing). Each section spans from its header (or document start) to the
    next header of any level, and later doubles as the "parent" range for
    parent-child chunking (principle 2)."""
    headers = [m.start() for m in _HEADER_RE.finditer(text)]
    if not headers or headers[0] != 0:
        headers = [0, *headers]
    headers = sorted(set(headers))
    sections = [
        _Span(start=start, end=(headers[i + 1] if i + 1 < len(headers) else len(text)))
        for i, start in enumerate(headers)
    ]
    return [s for s in sections if s.end > s.start] or [_Span(start=0, end=len(text))]


def _protected_spans(text: str) -> list[_Span]:
    """Character ranges that must never be split mid-way: fenced code blocks
    and Markdown tables."""
    spans: list[_Span] = []

    fence_positions = [m.start() for m in _FENCE_RE.finditer(text)]
    for i in range(0, len(fence_positions) - 1, 2):
        spans.append(_Span(fence_positions[i], fence_positions[i + 1] + 3))

    offset = 0
    table_start: int | None = None
    for line in text.splitlines(keepends=True):
        if "|" in line.strip():
            if table_start is None:
                table_start = offset
        elif table_start is not None:
            spans.append(_Span(table_start, offset))
            table_start = None
        offset += len(line)
    if table_start is not None:
        spans.append(_Span(table_start, offset))

    return spans


def _is_inside(pos: int, spans: list[_Span]) -> bool:
    return any(s.start <= pos < s.end for s in spans)


def _safe_break_points(text: str, protected: list[_Span]) -> list[int]:
    """Paragraph-boundary (blank line) break points that don't fall inside a
    protected span, plus the end of text as a guaranteed fallback break."""
    points = [m.end() for m in _BLANK_LINE_RE.finditer(text)]
    points.append(len(text))
    safe = [p for p in points if not _is_inside(p, protected)]
    return safe or [len(text)]


@CHUNKERS.register("markdown_aware")
class MarkdownAwareChunker(IChunker):
    """Layout-aware Markdown chunker (RAG principles 1 & 2).

    - Splits along Markdown section/paragraph boundaries and never cuts inside
      a fenced code block or table (principle 1).
    - Records the enclosing section's character range as `parent_char_start`/
      `parent_char_end` alongside each small "child" chunk used for dense
      embedding, enabling parent-chunk retrieval at generation time
      (principle 2). Parent text itself is not duplicated here — it is sliced
      on demand from `Document.content_markdown`.
    """

    def __init__(
        self,
        *,
        child_size: int = 380,
        child_overlap: int = 60,
        max_parent_size: int = 1800,
    ) -> None:
        self._child_size = child_size
        self._overlap = child_overlap
        self._max_parent = max_parent_size

    def chunk(self, text: str, *, document_id: str) -> list[dict[str, Any]]:
        if not text.strip():
            return []

        chunks: list[dict[str, Any]] = []
        idx = 0
        for section in _find_sections(text):
            section_text = text[section.start : section.end]
            parent_end = (
                section.start + self._max_parent
                if (section.end - section.start) > self._max_parent
                else section.end
            )

            if len(section_text) <= self._child_size:
                raw_chunk = section_text.strip("\n")
                if raw_chunk.strip():
                    chunks.append(
                        {
                            "chunk_id": f"{document_id}:{idx}",
                            "document_id": document_id,
                            "text": raw_chunk,
                            "char_start": section.start,
                            "char_end": section.end,
                            "page_number": None,
                            "chunk_index": idx,
                            "parent_char_start": section.start,
                            "parent_char_end": parent_end,
                        }
                    )
                    idx += 1
                continue

            protected = [
                _Span(s.start - section.start, s.end - section.start)
                for s in _protected_spans(section_text)
            ]
            breaks = _safe_break_points(section_text, protected)

            local_start = 0
            while local_start < len(section_text):
                target = min(local_start + self._child_size, len(section_text))
                for span in protected:
                    if span.start <= target < span.end:
                        target = span.end
                        break

                candidates = [b for b in breaks if local_start < b <= max(target, local_start + 1)]
                local_end = candidates[-1] if candidates else target
                local_end = min(max(local_end, local_start + 1), len(section_text))

                raw_chunk = section_text[local_start:local_end].strip("\n")
                if raw_chunk.strip():
                    abs_start = section.start + local_start
                    abs_end = section.start + local_end
                    chunks.append(
                        {
                            "chunk_id": f"{document_id}:{idx}",
                            "document_id": document_id,
                            "text": raw_chunk,
                            "char_start": abs_start,
                            "char_end": abs_end,
                            "page_number": None,
                            "chunk_index": idx,
                            "parent_char_start": section.start,
                            "parent_char_end": parent_end,
                        }
                    )
                    idx += 1

                if local_end >= len(section_text):
                    break
                local_start = max(local_end - self._overlap, local_start + 1)

        return chunks


@CHUNKERS.register("web_scrape")
class WebScrapeChunker(MarkdownAwareChunker):
    """Larger chunks for crawled HTML — doc sites (e.g. changelogs) can produce
    very long markdown; the default child_size would explode vector counts."""

    def __init__(self) -> None:
        super().__init__(child_size=1400, child_overlap=120, max_parent_size=3600)
