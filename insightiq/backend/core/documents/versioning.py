from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Document, DocumentChunk
from core.retrieval.qdrant_store import QdrantStore


def compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def guess_mime_type(filename: str, content_type: str | None = None) -> str:
    if content_type and content_type.strip():
        return content_type.split(";")[0].strip().lower()
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".doc"):
        return "application/msword"
    if lower.endswith(".pptx"):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if lower.endswith(".html") or lower.endswith(".htm"):
        return "text/html"
    if lower.endswith(".txt"):
        return "text/plain"
    return "application/octet-stream"


def build_enterprise_metadata(
    *,
    base: dict[str, Any] | None,
    source: str,
    extractor_used: str,
    confidence: float,
    graph_sync_status: str,
    version_number: int,
    content_hash: str,
    mime_type: str | None,
    file_size_bytes: int | None,
    page_count: int | None,
) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update(
        {
            "source": source,
            "extractor_used": extractor_used,
            "confidence": confidence,
            "graph_sync_status": graph_sync_status,
            "version_number": version_number,
            "content_hash": content_hash,
            "mime_type": mime_type,
            "file_size_bytes": file_size_bytes,
            "page_count": page_count,
            "indexed_at": datetime.now(UTC).isoformat(),
            "confidentiality": merged.get("confidentiality", "internal"),
            "retention_policy": merged.get("retention_policy", "standard"),
            "language": merged.get("language", "en"),
        }
    )
    return merged


async def resolve_document_version(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    filename: str,
    content_hash: str,
) -> tuple[uuid.UUID, int, Document | None, bool]:
    """Return ``(registry_id, next_version_number, current_doc_or_none, skip_index)``."""
    res = await session.execute(
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.collection_id == collection_id,
            Document.filename == filename,
            Document.is_current.is_(True),
        )
        .order_by(Document.version_number.desc())
        .limit(1)
    )
    current = res.scalar_one_or_none()
    if current is None:
        return uuid.uuid4(), 1, None, False
    if current.content_hash == content_hash:
        return current.registry_id, current.version_number, current, True
    return current.registry_id, current.version_number + 1, current, False


async def supersede_document(
    session: AsyncSession,
    store: QdrantStore,
    *,
    tenant_id: uuid.UUID,
    collection_id: str,
    current: Document,
) -> None:
    current.is_current = False
    current.status = "superseded"
    current.superseded_at = datetime.now(UTC)
    await session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == current.id)
        .values(version_number=current.version_number)
    )
    store.delete_document_points(collection_id, document_id=str(current.id))


async def chunk_count_for_document(session: AsyncSession, document_id: uuid.UUID) -> int:
    res = await session.execute(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    return int(res.scalar_one())
