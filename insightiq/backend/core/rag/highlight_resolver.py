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
    ref_index = 0

    for match in re.finditer(r"\[SOURCE:([^\]]+)\]", answer):
        start, end = match.span()
        html_parts.append(_escape(answer[last:start]))
        chunk_id = match.group(1)
        chunk = chunk_map.get(chunk_id)
        if chunk:
            ref_index += 1
            if chunk.document_id not in doc_colors:
                doc_colors[chunk.document_id] = DOC_COLORS[len(doc_colors) % len(DOC_COLORS)]
            color = doc_colors[chunk.document_id]
            snippet = chunk.text.strip().replace("\n", " ")
            if len(snippet) > 280:
                snippet = snippet[:277] + "..."
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
                    ref_index=ref_index,
                    text_snippet=snippet,
                )
            )
            html_parts.append(
                f'<sup><a href="#source-{ref_index}" data-chunk-id="{chunk_id}" '
                f'style="color:{color};text-decoration:none;font-weight:600">[{ref_index}]</a></sup>'
            )
        last = end

    html_parts.append(_escape(answer[last:]))
    clean = re.sub(r"\[SOURCE:[^\]]+\]", "", answer).strip()
    clean_with_refs = _inject_ref_markers(answer, chunk_map)
    answer_html = _replace_source_tags_with_refs(answer, chunk_map, doc_colors)
    if not answer_html.strip():
        answer_html = "".join(html_parts)
    return HighlightedResponse(
        answer=clean_with_refs or clean,
        answer_html=answer_html,
        highlight_spans=spans,
    )


def _inject_ref_markers(answer: str, chunk_map: dict[str, RetrievedChunk]) -> str:
    ref_index = 0
    seen: dict[str, int] = {}

    def repl(match: re.Match[str]) -> str:
        nonlocal ref_index
        chunk_id = match.group(1)
        if chunk_id not in seen:
            ref_index += 1
            seen[chunk_id] = ref_index
        return f" [{seen[chunk_id]}]"

    return re.sub(r"\[SOURCE:([^\]]+)\]", repl, answer).strip()


def _replace_source_tags_with_refs(
    answer: str,
    chunk_map: dict[str, RetrievedChunk],
    doc_colors: dict[str, str],
) -> str:
    ref_index = 0
    seen: dict[str, int] = {}
    parts: list[str] = []
    last = 0

    for match in re.finditer(r"\[SOURCE:([^\]]+)\]", answer):
        start, end = match.span()
        parts.append(_escape(answer[last:start]))
        chunk_id = match.group(1)
        chunk = chunk_map.get(chunk_id)
        if chunk:
            if chunk_id not in seen:
                ref_index += 1
                seen[chunk_id] = ref_index
                if chunk.document_id not in doc_colors:
                    doc_colors[chunk.document_id] = DOC_COLORS[len(doc_colors) % len(DOC_COLORS)]
            idx = seen[chunk_id]
            color = doc_colors.get(chunk.document_id, DOC_COLORS[0])
            parts.append(
                f'<sup><a href="#source-{idx}" data-chunk-id="{chunk_id}" '
                f'style="color:{color};text-decoration:none;font-weight:600">[{idx}]</a></sup>'
            )
        last = end

    parts.append(_escape(answer[last:]))
    return "".join(parts)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
