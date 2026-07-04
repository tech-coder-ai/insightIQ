from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.deps import get_db
from core.documents.versioning import chunk_count_for_document
from core.models import Document, DocumentChunk, DocumentCollection
from core.request_context import RequestContext, require_auth, require_role
from core.types import Role

router = APIRouter(prefix="/talk-to-docs", tags=["talk-to-docs-admin"])


class AdminSummaryResponse(BaseModel):
    collection_id: uuid.UUID
    collection_name: str
    rag_profile: str
    embedding_model: str
    document_count: int
    current_document_count: int
    chunk_count: int
    vector_points_estimate: int


class AdminDocumentRow(BaseModel):
    id: uuid.UUID
    registry_id: uuid.UUID
    filename: str
    version_number: int
    is_current: bool
    status: str
    content_hash: str | None
    mime_type: str | None
    file_size_bytes: int | None
    page_count: int | None
    chunk_count: int
    has_original: bool
    created_at: str
    metadata_json: dict


class AdminChunkRow(BaseModel):
    id: uuid.UUID
    chunk_id: str
    document_id: uuid.UUID
    filename: str
    version_number: int | None
    chunk_index: int
    char_start: int
    char_end: int
    page_number: int | None
    text_preview: str
    qdrant_point_id: str | None
    embedding_model: str | None
    document_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    bbox_json: dict | None = None
    highlight_regions: list | None = None


class DocumentVersionRow(BaseModel):
    id: uuid.UUID
    version_number: int
    is_current: bool
    status: str
    content_hash: str | None
    chunk_count: int
    created_at: str
    superseded_at: str | None = None


class PreviewRegionsResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    mime_type: str | None
    has_original: bool
    char_start: int
    char_end: int
    page_number: int | None
    highlight_regions: list
    text_snippet: str


@router.get("/collections/{collection_id}/admin/summary", response_model=AdminSummaryResponse)
async def admin_summary(
    collection_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> AdminSummaryResponse:
    col = await _get_collection(db, ctx.tenant_id, collection_id)
    doc_count = await _scalar(
        db,
        select(func.count()).select_from(Document).where(
            Document.collection_id == col.id, Document.tenant_id == ctx.tenant_id
        ),
    )
    current_count = await _scalar(
        db,
        select(func.count()).select_from(Document).where(
            Document.collection_id == col.id,
            Document.tenant_id == ctx.tenant_id,
            Document.is_current.is_(True),
        ),
    )
    chunk_count = await _scalar(
        db,
        select(func.count())
        .select_from(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.collection_id == col.id,
            DocumentChunk.tenant_id == ctx.tenant_id,
            Document.is_current.is_(True),
        ),
    )
    return AdminSummaryResponse(
        collection_id=col.id,
        collection_name=col.name,
        rag_profile=col.rag_profile,
        embedding_model=col.embedding_model,
        document_count=doc_count,
        current_document_count=current_count,
        chunk_count=chunk_count,
        vector_points_estimate=chunk_count,
    )


@router.get("/collections/{collection_id}/admin/documents", response_model=list[AdminDocumentRow])
async def admin_list_documents(
    collection_id: uuid.UUID,
    include_history: bool = Query(default=False),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[AdminDocumentRow]:
    col = await _get_collection(db, ctx.tenant_id, collection_id)
    stmt = select(Document).where(Document.collection_id == col.id, Document.tenant_id == ctx.tenant_id)
    if not include_history:
        stmt = stmt.where(Document.is_current.is_(True))
    stmt = stmt.order_by(Document.filename.asc(), Document.version_number.desc())
    res = await db.execute(stmt)
    rows: list[AdminDocumentRow] = []
    for doc in res.scalars().all():
        rows.append(
            AdminDocumentRow(
                id=doc.id,
                registry_id=doc.registry_id,
                filename=doc.filename,
                version_number=doc.version_number,
                is_current=doc.is_current,
                status=doc.status,
                content_hash=doc.content_hash,
                mime_type=doc.mime_type,
                file_size_bytes=doc.file_size_bytes,
                page_count=doc.page_count,
                chunk_count=await chunk_count_for_document(db, doc.id),
                has_original=bool(doc.storage_path and Path(doc.storage_path).exists()),
                created_at=doc.created_at.isoformat(),
                metadata_json=doc.metadata_json or {},
            )
        )
    return rows


@router.get("/collections/{collection_id}/admin/chunks", response_model=list[AdminChunkRow])
async def admin_list_chunks(
    collection_id: uuid.UUID,
    document_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[AdminChunkRow]:
    col = await _get_collection(db, ctx.tenant_id, collection_id)
    stmt = (
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.collection_id == col.id,
            DocumentChunk.tenant_id == ctx.tenant_id,
            Document.is_current.is_(True),
        )
        .order_by(Document.filename.asc(), DocumentChunk.chunk_index.asc())
        .offset(offset)
        .limit(limit)
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    if q and q.strip():
        stmt = stmt.where(DocumentChunk.text.ilike(f"%{q.strip()}%"))
    res = await db.execute(stmt)
    rows: list[AdminChunkRow] = []
    for chunk, doc in res.all():
        preview = chunk.text.strip().replace("\n", " ")
        if len(preview) > 240:
            preview = preview[:237] + "..."
        meta = doc.metadata_json or {}
        rows.append(
            AdminChunkRow(
                id=chunk.id,
                chunk_id=f"{chunk.document_id}:{chunk.chunk_index}",
                document_id=doc.id,
                filename=doc.filename,
                version_number=chunk.version_number or doc.version_number,
                chunk_index=chunk.chunk_index,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                page_number=chunk.page_number,
                text_preview=preview,
                qdrant_point_id=chunk.qdrant_point_id,
                embedding_model=col.embedding_model,
                document_type=meta.get("document_type"),
                tags=list(meta.get("tags") or []),
                bbox_json=chunk.bbox_json,
                highlight_regions=chunk.highlight_regions,
            )
        )
    return rows


@router.get("/documents/registry/{registry_id}/versions", response_model=list[DocumentVersionRow])
async def list_document_versions(
    registry_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentVersionRow]:
    res = await db.execute(
        select(Document)
        .where(Document.registry_id == registry_id, Document.tenant_id == ctx.tenant_id)
        .order_by(Document.version_number.desc())
    )
    rows: list[DocumentVersionRow] = []
    for doc in res.scalars().all():
        rows.append(
            DocumentVersionRow(
                id=doc.id,
                version_number=doc.version_number,
                is_current=doc.is_current,
                status=doc.status,
                content_hash=doc.content_hash,
                chunk_count=await chunk_count_for_document(db, doc.id),
                created_at=doc.created_at.isoformat(),
                superseded_at=doc.superseded_at.isoformat() if doc.superseded_at else None,
            )
        )
    return rows


@router.get("/documents/{document_id}/original")
async def get_document_original(
    document_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    doc = await _get_document(db, ctx.tenant_id, document_id)
    if not doc.storage_path:
        raise HTTPException(status_code=404, detail="original file not stored for this document version")
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="original file missing on disk")
    settings = get_settings_resolver().resolve()
    upload_root = Path(settings.storage.upload_dir).resolve()
    if not path.resolve().is_relative_to(upload_root):
        raise HTTPException(status_code=403, detail="invalid storage path")
    media = doc.mime_type or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=doc.filename)


@router.get("/documents/{document_id}/preview-regions", response_model=PreviewRegionsResponse)
async def get_preview_regions(
    document_id: uuid.UUID,
    char_start: int = Query(ge=0),
    char_end: int = Query(ge=0),
    chunk_id: str | None = Query(default=None),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> PreviewRegionsResponse:
    doc = await _get_document(db, ctx.tenant_id, document_id)
    regions: list = []
    page_number: int | None = None
    snippet = ""
    if chunk_id:
        from services.talk_to_docs.api import _resolve_chunk_row

        row = await _resolve_chunk_row(db, ctx.tenant_id, chunk_id)
        if row is not None:
            chunk, _doc = row
            regions = list(chunk.highlight_regions or [])
            page_number = chunk.page_number
            snippet = chunk.text.strip()
    if not regions and char_end > char_start:
        res = await db.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.tenant_id == ctx.tenant_id,
                DocumentChunk.char_start <= char_start,
                DocumentChunk.char_end >= char_end,
            )
        )
        chunk = res.scalar_one_or_none()
        if chunk is not None:
            regions = list(chunk.highlight_regions or [])
            page_number = chunk.page_number
            snippet = chunk.text.strip()
    content = doc.content_markdown or ""
    if not snippet and char_end > char_start:
        snippet = content[char_start:char_end].strip()
    return PreviewRegionsResponse(
        document_id=doc.id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        has_original=bool(doc.storage_path and Path(doc.storage_path).exists()),
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        highlight_regions=regions,
        text_snippet=snippet[:600],
    )


async def _get_collection(
    db: AsyncSession, tenant_id: uuid.UUID, collection_id: uuid.UUID
) -> DocumentCollection:
    res = await db.execute(
        select(DocumentCollection).where(
            DocumentCollection.id == collection_id,
            DocumentCollection.tenant_id == tenant_id,
        )
    )
    col = res.scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


async def _get_document(db: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    res = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    doc = res.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return doc


async def _scalar(db: AsyncSession, stmt) -> int:
    res = await db.execute(stmt)
    return int(res.scalar_one())
