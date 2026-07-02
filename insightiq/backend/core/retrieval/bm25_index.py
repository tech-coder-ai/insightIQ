from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

from core.rag.state import RetrievedChunk
from core.retrieval.lexical import tokenize
from core.retrieval.qdrant_store import QdrantStore

_CACHE_TTL_SECONDS = 300


@dataclass
class _CollectionIndex:
    bm25: BM25Okapi
    chunk_ids: list[str]
    payloads: list[dict[str, Any]]
    built_at: float = field(default_factory=time.time)


_INDEX_CACHE: dict[str, _CollectionIndex] = {}


def invalidate_bm25_cache(collection_id: str | None = None) -> None:
    """Drop cached BM25 indices so newly-ingested documents are searchable
    immediately instead of waiting for the TTL to expire."""
    if collection_id is None:
        _INDEX_CACHE.clear()
    else:
        _INDEX_CACHE.pop(collection_id, None)


class BM25Index:
    """Pure-Python BM25 sparse index (principle 4 — hybrid dense + sparse
    search), built on demand from the chunk text already stored in Qdrant
    payloads so no separate keyword search engine is required. Also backs the
    lexical reranker (principle 6)."""

    def __init__(self, store: QdrantStore | None = None) -> None:
        self._store = store or QdrantStore()

    async def _get_index(
        self, collection_id: str, tenant_id: str, metadata_filter: dict[str, Any] | None
    ) -> _CollectionIndex | None:
        cache_key = f"{collection_id}:{tenant_id}:{sorted((metadata_filter or {}).items())}"
        cached = _INDEX_CACHE.get(cache_key)
        if cached and (time.time() - cached.built_at) < _CACHE_TTL_SECONDS:
            return cached

        payloads = await self._store.scroll_all(collection_id, tenant_id=tenant_id, metadata_filter=metadata_filter)
        payloads = [p for p in payloads if str(p.get("text", "")).strip()]
        if not payloads:
            _INDEX_CACHE.pop(cache_key, None)
            return None

        corpus = [tokenize(p.get("text", "")) for p in payloads]
        bm25 = BM25Okapi(corpus)
        index = _CollectionIndex(bm25=bm25, chunk_ids=[str(p.get("chunk_id", "")) for p in payloads], payloads=payloads)
        _INDEX_CACHE[cache_key] = index
        return index

    async def search(
        self,
        collection_id: str,
        query: str,
        *,
        tenant_id: str,
        top_k: int = 10,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        index = await self._get_index(collection_id, tenant_id, metadata_filter)
        if index is None:
            return []
        scores = index.bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        chunks: list[RetrievedChunk] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            p = index.payloads[i]
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(p.get("chunk_id", "")),
                    document_id=str(p.get("document_id", "")),
                    text=str(p.get("text", "")),
                    char_start=int(p.get("char_start", 0)),
                    char_end=int(p.get("char_end", 0)),
                    page_number=p.get("page_number"),
                    relevance_score=float(scores[i]),
                    retriever_source="sparse",
                    parent_char_start=p.get("parent_char_start"),
                    parent_char_end=p.get("parent_char_end"),
                    document_type=p.get("document_type"),
                    tags=list(p.get("tags") or []),
                )
            )
        return chunks
