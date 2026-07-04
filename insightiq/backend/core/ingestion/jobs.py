from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import core.ingestion.chunkers.markdown_aware  # noqa: F401 — register chunker
import core.ingestion.chunkers.recursive  # noqa: F401 — register chunker (legacy/tests)
from core.documents.versioning import (
    build_enterprise_metadata,
    compute_content_hash,
    resolve_document_version,
    supersede_document,
)
from core.ingestion.chunkers.factory import CHUNKERS
from core.ingestion.pipeline_router import ExtractionResult, extract_document
from core.ingestion.span_mapper import assign_chunk_highlight_metadata
from core.ingestion.html_sanitize import sanitize_scraped_html
from core.ingestion.web_scraper import crawl
from core.models import Document, DocumentChunk
from core.retrieval.bm25_index import invalidate_bm25_cache
from core.retrieval.qdrant_store import QdrantStore

# Ordered stages, surfaced to the UI as a stepper.
STAGE_QUEUED = "queued"
STAGE_FETCHING = "fetching"
STAGE_EXTRACTING = "extracting"
STAGE_CHUNKING = "chunking"
STAGE_INDEXING = "indexing"
STAGE_SAVING = "saving"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"

FILE_STAGES = [STAGE_QUEUED, STAGE_EXTRACTING, STAGE_CHUNKING, STAGE_INDEXING, STAGE_SAVING, STAGE_COMPLETED]
SCRAPE_STAGES = [STAGE_QUEUED, STAGE_FETCHING, STAGE_EXTRACTING, STAGE_CHUNKING, STAGE_INDEXING, STAGE_SAVING, STAGE_COMPLETED]

_MAX_JOBS = 200


class IngestionJob(BaseModel):
    job_id: str
    kind: str  # "file" | "scrape"
    collection_id: str
    stages: list[str]
    stage: str = STAGE_QUEUED
    status: str = "processing"  # "processing" | "completed" | "failed"
    detail: str = "Queued"
    progress_current: int = 0
    progress_total: int = 0
    error: str | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


_JOBS: dict[str, IngestionJob] = {}


def _prune() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    for job_id in sorted(_JOBS, key=lambda k: _JOBS[k].created_at)[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(job_id, None)


def create_job(kind: str, collection_id: str) -> IngestionJob:
    job = IngestionJob(
        job_id=str(uuid.uuid4()),
        kind=kind,
        collection_id=collection_id,
        stages=FILE_STAGES if kind == "file" else SCRAPE_STAGES,
    )
    _JOBS[job.job_id] = job
    _prune()
    return job


def get_job(job_id: str) -> IngestionJob | None:
    return _JOBS.get(job_id)


def _set(job: IngestionJob, *, stage: str, detail: str) -> None:
    job.stage = stage
    job.detail = detail


_GRAPH_ENABLED_PROFILES = {"graph", "agentic"}
_MAX_GRAPH_SYNC_CHUNKS = 40
_SCRAPE_CHUNKER = "web_scrape"
_DEFAULT_CHUNKER = "markdown_aware"


async def _sync_chunks_to_graph(
    chunks: list[dict[str, Any]], *, tenant_id: str, collection_id: str, document_id: str
) -> str:
    """Entity/relationship extraction as an ingestion stage (Workstream 2 —
    GraphRAG). Best-effort: ingestion still succeeds even if Neo4j is
    unreachable or misconfigured, it just skips graph sync for this document."""
    try:
        from core.graph.entity_extractor import extract_entities
        from core.graph.neo4j_store import Neo4jStore

        store = Neo4jStore()
        synced_any = False
        for c in chunks[:_MAX_GRAPH_SYNC_CHUNKS]:
            extraction = await extract_entities(c["text"])
            if not extraction.entities:
                continue
            await store.upsert_chunk_graph(
                tenant_id=tenant_id,
                collection_id=collection_id,
                document_id=document_id,
                chunk_id=c["chunk_id"],
                chunk_text=c["text"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                entities=[e.model_dump() for e in extraction.entities],
                relationships=[r.model_dump() for r in extraction.relationships],
            )
            synced_any = True
        return "ok" if synced_any else "no_entities"
    except Exception:  # noqa: BLE001 - Neo4j is optional; ingestion must not fail because of it
        return "error"


async def _index_markdown(
    session: Any,
    store: QdrantStore,
    *,
    markdown: str,
    filename: str,
    collection_id: str,
    tenant_id: str,
    embedding_model: str,
    extractor_used: str,
    confidence: float,
    metadata: dict[str, Any] | None = None,
    rag_profile: str = "standard",
    storage_path: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    page_count: int | None = None,
    text_spans: list[dict[str, Any]] | None = None,
    ingested_by: uuid.UUID | None = None,
    source: str = "upload",
) -> dict[str, Any]:
    """Chunk, embed/index, and persist a single document version."""
    content_hash = compute_content_hash(markdown)
    registry_id, version_number, current_doc, skip_index = await resolve_document_version(
        session,
        tenant_id=uuid.UUID(tenant_id),
        collection_id=uuid.UUID(collection_id),
        filename=filename,
        content_hash=content_hash,
    )
    if skip_index and current_doc is not None:
        return {
            "document_id": str(current_doc.id),
            "registry_id": str(current_doc.registry_id),
            "filename": filename,
            "chunks": await _chunk_count(session, current_doc.id),
            "version_number": current_doc.version_number,
            "skipped": True,
            "message": "Document unchanged — current version already indexed.",
        }

    if current_doc is not None:
        await supersede_document(
            session,
            store,
            tenant_id=uuid.UUID(tenant_id),
            collection_id=collection_id,
            current=current_doc,
        )

    doc_id = uuid.uuid4()
    chunker_key = _SCRAPE_CHUNKER if source == "scrape" else _DEFAULT_CHUNKER
    chunks = CHUNKERS.create(chunker_key).chunk(markdown, document_id=str(doc_id))
    assign_chunk_highlight_metadata(chunks, text_spans or [])

    document_type = (metadata or {}).get("document_type")
    tags = (metadata or {}).get("tags") or []
    for c in chunks:
        c["is_current"] = True
        c["version_number"] = version_number
        c["registry_id"] = str(registry_id)
        if document_type:
            c["document_type"] = document_type
        if tags:
            c["tags"] = tags

    await store.upsert_chunks(
        collection_id,
        tenant_id=tenant_id,
        chunks=chunks,
        embedder_key=embedding_model,
    )
    invalidate_bm25_cache(collection_id)

    graph_sync_status = "skipped"
    if rag_profile in _GRAPH_ENABLED_PROFILES:
        graph_sync_status = await _sync_chunks_to_graph(
            chunks, tenant_id=tenant_id, collection_id=collection_id, document_id=str(doc_id)
        )

    doc_metadata = build_enterprise_metadata(
        base=metadata,
        source=source,
        extractor_used=extractor_used,
        confidence=confidence,
        graph_sync_status=graph_sync_status,
        version_number=version_number,
        content_hash=content_hash,
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        page_count=page_count,
    )
    session.add(
        Document(
            id=doc_id,
            registry_id=registry_id,
            collection_id=uuid.UUID(collection_id),
            tenant_id=uuid.UUID(tenant_id),
            filename=filename,
            content_markdown=markdown,
            metadata_json=doc_metadata,
            version_number=version_number,
            is_current=True,
            storage_path=storage_path,
            mime_type=mime_type,
            content_hash=content_hash,
            status="active",
            file_size_bytes=file_size_bytes,
            page_count=page_count,
            ingested_by=ingested_by,
        )
    )
    for c in chunks:
        session.add(
            DocumentChunk(
                document_id=doc_id,
                collection_id=uuid.UUID(collection_id),
                tenant_id=uuid.UUID(tenant_id),
                chunk_index=c["chunk_index"],
                text=c["text"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                page_number=c.get("page_number"),
                qdrant_point_id=c.get("qdrant_point_id"),
                parent_char_start=c.get("parent_char_start"),
                parent_char_end=c.get("parent_char_end"),
                bbox_json=c.get("bbox_json"),
                highlight_regions=c.get("highlight_regions"),
                version_number=version_number,
            )
        )
    return {
        "document_id": str(doc_id),
        "registry_id": str(registry_id),
        "filename": filename,
        "chunks": len(chunks),
        "version_number": version_number,
        "content_hash": content_hash,
        "skipped": False,
    }


async def _chunk_count(session: Any, document_id: uuid.UUID) -> int:
    from sqlalchemy import func, select

    res = await session.execute(
        select(func.count()).select_from(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    return int(res.scalar_one())


async def run_file_ingestion(
    job_id: str,
    *,
    file_path: str,
    filename: str,
    collection_id: str,
    tenant_id: str,
    embedding_model: str,
    metadata: dict[str, Any] | None = None,
    rag_profile: str = "standard",
    mime_type: str | None = None,
    ingested_by: uuid.UUID | None = None,
) -> None:
    from core.deps import get_app_sessionmaker

    job = _JOBS[job_id]
    try:
        _set(job, stage=STAGE_EXTRACTING, detail=f"Extracting text from {filename}…")
        extraction = await extract_document(file_path)
        if not extraction.markdown.strip():
            raise ValueError("no readable text could be extracted from this file")

        _set(job, stage=STAGE_CHUNKING, detail="Splitting into chunks…")
        store = QdrantStore()
        file_size = Path(file_path).stat().st_size if Path(file_path).exists() else None

        _set(job, stage=STAGE_INDEXING, detail="Generating embeddings and indexing…")
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as session:
            summary = await _index_markdown(
                session,
                store,
                markdown=extraction.markdown,
                filename=filename,
                collection_id=collection_id,
                tenant_id=tenant_id,
                embedding_model=embedding_model,
                extractor_used=extraction.extractor_used,
                confidence=extraction.confidence,
                metadata=metadata,
                rag_profile=rag_profile,
                storage_path=file_path,
                mime_type=mime_type,
                file_size_bytes=file_size,
                page_count=extraction.page_count,
                text_spans=extraction.text_spans,
                ingested_by=ingested_by,
                source="upload",
            )
            _set(job, stage=STAGE_SAVING, detail="Saving to database…")
            await session.commit()

        job.documents = [summary]
        job.progress_current = 1
        job.progress_total = 1
        job.status = "completed"
        if summary.get("skipped"):
            _set(job, stage=STAGE_COMPLETED, detail=str(summary.get("message", "Already up to date.")))
        else:
            _set(
                job,
                stage=STAGE_COMPLETED,
                detail=f"Indexed v{summary['version_number']} — {summary['chunks']} chunks.",
            )
    except Exception as exc:  # noqa: BLE001 - report the failing stage to the UI
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"


async def run_scrape_ingestion(
    job_id: str,
    *,
    url: str,
    depth: int,
    max_pages: int,
    collection_id: str,
    tenant_id: str,
    embedding_model: str,
    rag_profile: str = "standard",
    ingested_by: uuid.UUID | None = None,
) -> None:
    from core.deps import get_app_sessionmaker

    job = _JOBS[job_id]
    try:
        _set(job, stage=STAGE_FETCHING, detail=f"Crawling {url}…")
        job.progress_total = max_pages

        async def _on_progress(current: int, total: int) -> None:
            job.progress_current = current
            job.detail = f"Fetched {current} page(s)…"

        pages = await crawl(url, depth=depth, max_pages=max_pages, on_progress=_on_progress)
        if not pages:
            raise ValueError("no pages could be fetched (check the URL is reachable and returns HTML)")

        store = QdrantStore()
        sessionmaker = get_app_sessionmaker()
        summaries: list[dict[str, Any]] = []
        job.progress_total = len(pages)

        failures: list[str] = []
        async with sessionmaker() as session:
            for idx, (page_url, html) in enumerate(pages, start=1):
                _set(job, stage=STAGE_EXTRACTING, detail=f"Processing {page_url} ({idx}/{len(pages)})…")
                cleaned_html = sanitize_scraped_html(html)
                with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
                    tmp.write(cleaned_html)
                    tmp_path = tmp.name
                try:
                    extraction = await extract_document(tmp_path)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

                if not extraction.markdown.strip():
                    continue

                _set(job, stage=STAGE_INDEXING, detail=f"Embedding page {idx}/{len(pages)}…")
                try:
                    summary = await _index_markdown(
                        session,
                        store,
                        markdown=extraction.markdown,
                        filename=page_url,
                        collection_id=collection_id,
                        tenant_id=tenant_id,
                        embedding_model=embedding_model,
                        extractor_used=extraction.extractor_used,
                        confidence=extraction.confidence,
                        metadata={"source": "scrape", "source_url": page_url},
                        rag_profile=rag_profile,
                        mime_type="text/html",
                        page_count=extraction.page_count,
                        text_spans=extraction.text_spans,
                        ingested_by=ingested_by,
                        source="scrape",
                    )
                    await session.commit()
                    summaries.append(summary)
                    job.progress_current = idx
                except Exception as exc:  # noqa: BLE001 - continue other pages; report below
                    await session.rollback()
                    failures.append(f"{page_url}: {type(exc).__name__}: {exc}")

        if not summaries:
            hint = failures[0] if failures else "no extractable text"
            raise ValueError(f"scrape indexing failed — {hint}")

        job.documents = summaries
        total_chunks = sum(s["chunks"] for s in summaries)
        job.status = "completed"
        detail = f"Indexed {len(summaries)} page(s), {total_chunks} chunks."
        if failures:
            detail += f" {len(failures)} page(s) failed."
        _set(job, stage=STAGE_COMPLETED, detail=detail)
        if failures:
            job.error = "; ".join(failures[:3]) + ("…" if len(failures) > 3 else "")
    except Exception as exc:  # noqa: BLE001 - report the failing stage to the UI
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
