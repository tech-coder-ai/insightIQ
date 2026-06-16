from __future__ import annotations

import re

from core.rag.state import HighlightSpan, HighlightedResponse, RetrievedChunk

DOC_COLORS = ["#58a6ff", "#3fb950", "#d29922", "#f778ba", "#a371f7"]


def resolve_highlights(
    answer: str,
    chunks: list[RetrievedChunk],
    *,
    chunk_map: dict[str, RetrievedChunk] | None = None,
) -> HighlightedResponse:
    chunk_map = chunk_map or {c.chunk_id: c for c in chunks}
    doc_colors: dict[str, str] = {}
    spans: list[HighlightSpan] = []
    html_parts: list[str] = []
    last = 0

    for match in re.finditer(r"\[SOURCE:([^\]]+)\]", answer):
        start, end = match.span()
        html_parts.append(_escape(answer[last:start]))
        chunk_id = match.group(1)
        chunk = chunk_map.get(chunk_id)
        if chunk:
            if chunk.document_id not in doc_colors:
                doc_colors[chunk.document_id] = DOC_COLORS[len(doc_colors) % len(DOC_COLORS)]
            color = doc_colors[chunk.document_id]
            spans.append(
                HighlightSpan(
                    chunk_id=chunk_id,
                    document_id=chunk.document_id,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    page_number=chunk.page_number,
                    color=color,
                    relevance_score=chunk.relevance_score,
                    rerank_score=chunk.rerank_score,
                )
            )
            html_parts.append(
                f'<cite data-chunk-id="{chunk_id}" style="color:{color}">{_escape(chunk.text[:120])}</cite>'
            )
        last = end

    html_parts.append(_escape(answer[last:]))
    clean = re.sub(r"\[SOURCE:[^\]]+\]", "", answer).strip()
    answer_html = "".join(html_parts)
    return HighlightedResponse(answer=clean, answer_html=answer_html, highlight_spans=spans)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
