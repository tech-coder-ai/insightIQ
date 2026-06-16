from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

import core.ingestion.chunkers.recursive  # noqa: F401 — register chunker
from core.ingestion.chunkers.factory import CHUNKERS
from core.ingestion.pipeline_router import extract_document
from core.ingestion.web_scraper import crawl
from core.models import Document, DocumentChunk
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
) -> dict[str, Any]:
    """Chunk, embed/index, and persist a single document. Returns a summary dict."""
    doc_id = uuid.uuid4()
    chunks = CHUNKERS.create("recursive").chunk(markdown, document_id=str(doc_id))

    await store.upsert_chunks(
        collection_id,
        tenant_id=tenant_id,
        chunks=chunks,
        embedder_key=embedding_model,
    )

    session.add(
        Document(
            id=doc_id,
            collection_id=uuid.UUID(collection_id),
            tenant_id=uuid.UUID(tenant_id),
            filename=filename,
            content_markdown=markdown,
            metadata_json={"extractor_used": extractor_used, "confidence": confidence},
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
            )
        )
    return {"document_id": str(doc_id), "filename": filename, "chunks": len(chunks)}


async def run_file_ingestion(
    job_id: str,
    *,
    file_path: str,
    filename: str,
    collection_id: str,
    tenant_id: str,
    embedding_model: str,
) -> None:
    from core.deps import get_app_sessionmaker

    job = _JOBS[job_id]
    try:
        _set(job, stage=STAGE_EXTRACTING, detail=f"Extracting text from {filename}…")
        markdown, extractor_used, confidence = await extract_document(file_path)
        if not markdown.strip():
            raise ValueError("no readable text could be extracted from this file")

        _set(job, stage=STAGE_CHUNKING, detail="Splitting into chunks…")
        store = QdrantStore()

        _set(job, stage=STAGE_INDEXING, detail="Generating embeddings and indexing…")
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as session:
            summary = await _index_markdown(
                session,
                store,
                markdown=markdown,
                filename=filename,
                collection_id=collection_id,
                tenant_id=tenant_id,
                embedding_model=embedding_model,
                extractor_used=extractor_used,
                confidence=confidence,
            )
            _set(job, stage=STAGE_SAVING, detail="Saving to database…")
            await session.commit()

        job.documents = [summary]
        job.progress_current = 1
        job.progress_total = 1
        job.status = "completed"
        _set(job, stage=STAGE_COMPLETED, detail=f"Indexed {summary['chunks']} chunks.")
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

        async with sessionmaker() as session:
            for idx, (page_url, html) in enumerate(pages, start=1):
                _set(job, stage=STAGE_EXTRACTING, detail=f"Processing {page_url} ({idx}/{len(pages)})…")
                with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as tmp:
                    tmp.write(html)
                    tmp_path = tmp.name
                try:
                    markdown, extractor_used, confidence = await extract_document(tmp_path)
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

                if not markdown.strip():
                    continue

                _set(job, stage=STAGE_INDEXING, detail=f"Indexing {page_url} ({idx}/{len(pages)})…")
                summary = await _index_markdown(
                    session,
                    store,
                    markdown=markdown,
                    filename=page_url,
                    collection_id=collection_id,
                    tenant_id=tenant_id,
                    embedding_model=embedding_model,
                    extractor_used=extractor_used,
                    confidence=confidence,
                )
                summaries.append(summary)
                job.progress_current = idx

            _set(job, stage=STAGE_SAVING, detail="Saving to database…")
            await session.commit()

        if not summaries:
            raise ValueError("pages were fetched but contained no extractable text")

        job.documents = summaries
        total_chunks = sum(s["chunks"] for s in summaries)
        job.status = "completed"
        _set(job, stage=STAGE_COMPLETED, detail=f"Indexed {len(summaries)} page(s), {total_chunks} chunks.")
    except Exception as exc:  # noqa: BLE001 - report the failing stage to the UI
        job.status = "failed"
        job.error = f"{type(exc).__name__}: {exc}"
