from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.deps import get_db
import core.ingestion.chunkers.recursive  # noqa: F401 — register chunker
from core.ingestion.chunkers.factory import CHUNKERS
from core.ingestion.pipeline_router import extract_document
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


@router.post("/collections/{collection_id}/upload")
async def upload_document(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    col = await _get_collection(db, ctx.tenant_id, collection_id)
    settings = get_settings_resolver().resolve()
    upload_dir = Path(settings.storage.upload_dir) / str(col.tenant_id) / str(col.id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    doc_id = uuid.uuid4()
    dest = upload_dir / f"{doc_id}_{file.filename}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    markdown, extractor_used, confidence = await extract_document(str(dest))
    chunker = CHUNKERS.create("recursive")
    chunks = chunker.chunk(markdown, document_id=str(doc_id))

    store = QdrantStore()
    collection_name = str(col.id)
    await store.upsert_chunks(
        collection_name,
        tenant_id=str(ctx.tenant_id),
        chunks=chunks,
        embedder_key=col.embedding_model,
    )

    doc = Document(
        id=doc_id,
        collection_id=col.id,
        tenant_id=ctx.tenant_id,
        filename=file.filename or "upload",
        content_markdown=markdown,
        metadata_json={"extractor_used": extractor_used, "confidence": confidence},
    )
    db.add(doc)
    for c in chunks:
        db.add(
            DocumentChunk(
                document_id=doc_id,
                collection_id=col.id,
                tenant_id=ctx.tenant_id,
                chunk_index=c["chunk_index"],
                text=c["text"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                page_number=c.get("page_number"),
                qdrant_point_id=c.get("qdrant_point_id"),
            )
        )
    await db.commit()
    return {"document_id": str(doc_id), "extractor_used": extractor_used, "chunks": str(len(chunks))}


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

    await _ensure_conversation(db, ctx, conversation_id, req.question)
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
    db: AsyncSession, ctx: RequestContext, conversation_id: uuid.UUID, question: str
) -> None:
    res = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == ctx.tenant_id,
            Conversation.user_id == ctx.user_id,
        )
    )
    if res.scalar_one_or_none() is None:
        title = question[:80] + ("..." if len(question) > 80 else "")
        db.add(
            Conversation(
                id=conversation_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                title=title,
            )
        )
