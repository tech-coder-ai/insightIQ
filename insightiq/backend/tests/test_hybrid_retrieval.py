from __future__ import annotations

from typing import Any

import pytest

from core.rag.fusion import reciprocal_rank_fusion
from core.rag.state import RetrievedChunk
from core.retrieval.bm25_index import BM25Index, invalidate_bm25_cache
from core.retrieval.lexical import tokenize
from core.retrieval.rerankers.heuristic import LexicalBM25Reranker, NoOpReranker


class _FakeQdrantStore:
    """Stands in for QdrantStore so BM25Index can be unit tested without a
    live Qdrant instance."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads

    async def scroll_all(
        self,
        collection_name: str,
        *,
        tenant_id: str,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        if metadata_filter:
            return [
                p
                for p in self._payloads
                if all(p.get(k) == v for k, v in metadata_filter.items())
            ]
        return self._payloads


_PAYLOADS = [
    {
        "chunk_id": "c1",
        "document_id": "d1",
        "text": "Quarterly revenue grew 20% driven by strong enterprise sales.",
        "char_start": 0,
        "char_end": 60,
        "document_type": "financial_report",
    },
    {
        "chunk_id": "c2",
        "document_id": "d1",
        "text": "The company hired a new head of marketing in the third quarter.",
        "char_start": 61,
        "char_end": 120,
        "document_type": "press_release",
    },
    {
        "chunk_id": "c3",
        "document_id": "d2",
        "text": "Revenue guidance for next year was raised after strong bookings.",
        "char_start": 0,
        "char_end": 65,
        "document_type": "financial_report",
    },
]


def test_tokenize_lowercases_and_extracts_alphanumeric() -> None:
    assert tokenize("Revenue Grew 20%!!") == ["revenue", "grew", "20"]
    assert tokenize(None) == []
    assert tokenize("") == []


@pytest.mark.asyncio
async def test_bm25_index_ranks_relevant_chunk_first() -> None:
    invalidate_bm25_cache()
    index = BM25Index(store=_FakeQdrantStore(_PAYLOADS))  # type: ignore[arg-type]
    results = await index.search("col-1", "revenue growth guidance", tenant_id="t1", top_k=5)

    assert results, "expected at least one BM25 match"
    assert all(r.retriever_source == "sparse" for r in results)
    # The two revenue-related chunks should outrank the unrelated marketing one.
    top_ids = {r.chunk_id for r in results[:2]}
    assert top_ids == {"c1", "c3"}


@pytest.mark.asyncio
async def test_bm25_index_respects_metadata_filter() -> None:
    invalidate_bm25_cache()
    index = BM25Index(store=_FakeQdrantStore(_PAYLOADS))  # type: ignore[arg-type]
    results = await index.search(
        "col-1",
        "revenue",
        tenant_id="t1",
        top_k=5,
        metadata_filter={"document_type": "press_release"},
    )
    # Only the marketing chunk matches the filter, and it has no lexical
    # overlap with "revenue" so BM25 should return nothing.
    assert results == []


@pytest.mark.asyncio
async def test_bm25_index_returns_none_for_empty_collection() -> None:
    invalidate_bm25_cache()
    index = BM25Index(store=_FakeQdrantStore([]))  # type: ignore[arg-type]
    results = await index.search("col-empty", "anything", tenant_id="t1")
    assert results == []


def test_reciprocal_rank_fusion_merges_dense_and_sparse_sources() -> None:
    dense = [
        RetrievedChunk(chunk_id="a", document_id="d1", text="alpha", char_start=0, char_end=5, retriever_source="dense"),
        RetrievedChunk(chunk_id="b", document_id="d1", text="beta", char_start=6, char_end=10, retriever_source="dense"),
    ]
    sparse = [
        RetrievedChunk(chunk_id="b", document_id="d1", text="beta", char_start=6, char_end=10, retriever_source="sparse"),
        RetrievedChunk(chunk_id="c", document_id="d1", text="gamma", char_start=11, char_end=16, retriever_source="sparse"),
    ]
    fused = reciprocal_rank_fusion([dense, sparse])
    fused_ids = [c.chunk_id for c in fused]
    assert set(fused_ids) == {"a", "b", "c"}
    # "b" appears in both lists so it should be ranked ahead of chunks that
    # only appear in a single retriever's results.
    assert fused_ids[0] == "b"


@pytest.mark.asyncio
async def test_lexical_bm25_reranker_orders_by_query_overlap() -> None:
    chunks = [
        RetrievedChunk(chunk_id="c1", document_id="d1", text="The weather today is sunny and warm.", char_start=0, char_end=10),
        RetrievedChunk(chunk_id="c2", document_id="d1", text="Quarterly revenue grew twenty percent year over year.", char_start=0, char_end=10),
    ]
    reranker = LexicalBM25Reranker()
    ranked = await reranker.rerank("quarterly revenue growth", chunks, top_k=2)
    assert ranked[0].chunk_id == "c2"
    assert ranked[0].rerank_score is not None
    assert ranked[0].rerank_score >= ranked[1].rerank_score


@pytest.mark.asyncio
async def test_lexical_bm25_reranker_handles_empty_input() -> None:
    reranker = LexicalBM25Reranker()
    assert await reranker.rerank("anything", [], top_k=5) == []


@pytest.mark.asyncio
async def test_noop_reranker_truncates_to_top_k() -> None:
    chunks = [
        RetrievedChunk(chunk_id=str(i), document_id="d1", text="x", char_start=0, char_end=1)
        for i in range(5)
    ]
    reranker = NoOpReranker()
    ranked = await reranker.rerank("q", chunks, top_k=2)
    assert len(ranked) == 2
    assert [c.chunk_id for c in ranked] == ["0", "1"]
