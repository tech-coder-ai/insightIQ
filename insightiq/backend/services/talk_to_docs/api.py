from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.deps import get_db
from core.ingestion.jobs import (
    IngestionJob,
    create_job,
    get_job,
    run_file_ingestion,
    run_scrape_ingestion,
)
from core.models import ChatMessage, Conversation, Document, DocumentChunk, DocumentCollection
from core.rag.engine import RagEngine
from core.rag.profiles import load_profile
from core.request_context import RequestContext, require_auth, require_role
from core.retrieval.qdrant_store import QdrantStore
from core.types import Role

router = APIRouter(prefix="/talk-to-docs", tags=["talk-to-docs"])


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    rag_profile: str
    embedding_model: str


class DocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    has_content: bool
    created_at: str


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rag_profile: str = "naive"


class AskDocsRequest(BaseModel):
    collection_id: uuid.UUID
    question: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None
    profile_override: str | None = None


class AskDocsResponse(BaseModel):
    conversation_id: uuid.UUID
    answer: str
    answer_html: str
    highlight_spans: list[dict]
    rag_profile_snapshot: dict
    trace: dict


@router.post("/collections", response_model=CollectionResponse)
async def create_collection(
    req: CreateCollectionRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> CollectionResponse:
    try:
        load_profile(req.rag_profile)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    col = DocumentCollection(
        tenant_id=ctx.tenant_id,
        name=req.name,
        rag_profile=req.rag_profile,
    )
    db.add(col)
    await db.commit()
    await db.refresh(col)
    return CollectionResponse(
        id=col.id, name=col.name, rag_profile=col.rag_profile, embedding_model=col.embedding_model
    )


@router.get("/collections", response_model=list[CollectionResponse])
async def list_collections(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[CollectionResponse]:
    res = await db.execute(
        select(DocumentCollection).where(DocumentCollection.tenant_id == ctx.tenant_id)
    )
    return [
        CollectionResponse(
            id=c.id, name=c.name, rag_profile=c.rag_profile, embedding_model=c.embedding_model
        )
        for c in res.scalars().all()
    ]


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    collection_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DocumentResponse]:
    await _get_collection(db, ctx.tenant_id, collection_id)
    res = await db.execute(
        select(Document)
        .where(Document.collection_id == collection_id, Document.tenant_id == ctx.tenant_id)
        .order_by(Document.created_at.desc())
    )
    return [
        DocumentResponse(
            id=d.id,
            filename=d.filename,
            has_content=bool((d.content_markdown or "").strip()),
            created_at=d.created_at.isoformat(),
        )
        for d in res.scalars().all()
    ]


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    col = await _get_collection(db, ctx.tenant_id, collection_id)

    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.collection_id == col.id, DocumentChunk.tenant_id == ctx.tenant_id
        )
    )
    await db.execute(
        delete(Document).where(
            Document.collection_id == col.id, Document.tenant_id == ctx.tenant_id
        )
    )
    await db.delete(col)
    await db.commit()

    try:
        QdrantStore().delete_collection(str(col.id))
    except Exception:  # noqa: BLE001 - vector store cleanup is best-effort
        pass

    return {"status": "deleted", "collection_id": str(col.id)}


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=4)
    depth: int = Field(default=0, ge=0, le=5)
    max_pages: int = Field(default=20, ge=1, le=100)


@router.post("/collections/{collection_id}/upload", response_model=IngestionJob)
async def upload_document(
    collection_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> IngestionJob:
    col = await _get_collection(db, ctx.tenant_id, collection_id)

    settings = get_settings_resolver().resolve()
    upload_dir = Path(settings.storage.upload_dir) / str(col.tenant_id) / str(col.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{uuid.uuid4()}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    job = create_job("file", str(col.id))
    background.add_task(
        run_file_ingestion,
        job.job_id,
        file_path=str(dest),
        filename=file.filename or "upload",
        collection_id=str(col.id),
        tenant_id=str(ctx.tenant_id),
        embedding_model=col.embedding_model,
    )
    return job


@router.post("/collections/{collection_id}/scrape", response_model=IngestionJob)
async def scrape_url(
    collection_id: uuid.UUID,
    req: ScrapeRequest,
    background: BackgroundTasks,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> IngestionJob:
    col = await _get_collection(db, ctx.tenant_id, collection_id)

    job = create_job("scrape", str(col.id))
    background.add_task(
        run_scrape_ingestion,
        job.job_id,
        url=req.url,
        depth=req.depth,
        max_pages=req.max_pages,
        collection_id=str(col.id),
        tenant_id=str(ctx.tenant_id),
        embedding_model=col.embedding_model,
    )
    return job


@router.get("/jobs/{job_id}", response_model=IngestionJob)
async def get_ingestion_job(
    job_id: str,
    ctx: RequestContext = Depends(require_auth),
) -> IngestionJob:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ingestion job not found or expired")
    return job


@router.post("/ask", response_model=AskDocsResponse)
async def ask_documents(
    req: AskDocsRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> AskDocsResponse:
    col = await _get_collection(db, ctx.tenant_id, req.collection_id)
    profile_name = req.profile_override or col.rag_profile
    profile_cfg = load_profile(profile_name)
    conversation_id = req.conversation_id or uuid.uuid4()

    engine = RagEngine()
    result = await engine.run(
        query=req.question,
        tenant_id=str(ctx.tenant_id),
        collection_ids=[str(col.id)],
        profile_name=profile_name,
    )

    final = result.get("final") or {}
    answer = final.get("answer", "")
    answer_html = final.get("answer_html", answer)
    highlights = final.get("highlight_spans", [])

    await _ensure_conversation(db, ctx, conversation_id, col.id, req.question)
    snapshot = profile_cfg.model_dump()

    user_msg = ChatMessage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation_id=conversation_id,
        role="user",
        content=req.question,
        metadata_json={"collection_id": str(col.id), "rag_profile_snapshot_json": snapshot},
    )
    assistant_msg = ChatMessage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        metadata_json={
            "highlight_spans_json": highlights,
            "answer_html": answer_html,
            "rag_profile_snapshot_json": snapshot,
            "retrieval_round": result.get("retrieval_round", 0),
        },
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()

    return AskDocsResponse(
        conversation_id=conversation_id,
        answer=answer,
        answer_html=answer_html,
        highlight_spans=highlights,
        rag_profile_snapshot=snapshot,
        trace=result.get("trace", {}),
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


async def _ensure_conversation(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    collection_id: uuid.UUID,
    question: str,
) -> None:
    res = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == ctx.tenant_id,
            Conversation.user_id == ctx.user_id,
        )
    )
    title = question[:80] + ("..." if len(question) > 80 else "")
    conv = res.scalar_one_or_none()
    if conv is None:
        db.add(
            Conversation(
                id=conversation_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                title=title,
                # `datasource_id` doubles as the collection association for docs chats.
                datasource_id=collection_id,
            )
        )
    elif conv.datasource_id is None:
        conv.datasource_id = collection_id
