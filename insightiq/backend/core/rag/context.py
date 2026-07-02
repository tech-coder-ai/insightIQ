from __future__ import annotations

import uuid
from typing import Any

from core.rag.state import RetrievedChunk


async def hydrate_parent_context(chunks: list[RetrievedChunk], db: Any | None) -> None:
    """Parent-child chunking (principle 2): expand each chunk's LLM-facing
    context (`context_text`) to its enclosing parent section by slicing the
    full document text using the offsets captured at ingestion time. The
    small, precise child `text`/`char_start`/`char_end` are left untouched so
    citations and highlighting stay accurate.

    Best-effort: silently leaves `context_text` unset (callers fall back to
    `text`) when no DB session is available or a document/offset is missing —
    e.g. in unit tests that exercise the graph without a database.
    """
    if db is None:
        return

    doc_ids: set[str] = set()
    for c in chunks:
        if c.parent_char_start is not None and c.parent_char_end is not None and c.document_id:
            doc_ids.add(c.document_id)
    if not doc_ids:
        return

    try:
        valid_ids = [uuid.UUID(d) for d in doc_ids]
    except ValueError:
        return

    from sqlalchemy import select

    from core.models import Document

    res = await db.execute(select(Document.id, Document.content_markdown).where(Document.id.in_(valid_ids)))
    text_by_doc = {str(doc_id): content or "" for doc_id, content in res.all()}

    for c in chunks:
        content = text_by_doc.get(c.document_id)
        if not content or c.parent_char_start is None or c.parent_char_end is None:
            continue
        start = max(0, min(c.parent_char_start, len(content)))
        end = max(start, min(c.parent_char_end, len(content)))
        parent_text = content[start:end].strip()
        if parent_text:
            c.context_text = parent_text
