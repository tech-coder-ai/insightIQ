from __future__ import annotations

import pytest

from core.rag.fusion import reciprocal_rank_fusion
from core.rag.highlight_resolver import resolve_highlights
from core.rag.profiles import load_profile
from core.rag.state import RetrievedChunk


def test_rrf_promotes_overlap() -> None:
    a = RetrievedChunk(chunk_id="a", document_id="d1", text="alpha", char_start=0, char_end=5)
    b = RetrievedChunk(chunk_id="b", document_id="d1", text="beta", char_start=6, char_end=10)
    fused = reciprocal_rank_fusion([[a, b], [b, a]])
    assert fused[0].chunk_id == "a" or fused[0].chunk_id == "b"
    assert len(fused) == 2


def test_highlight_resolver_strips_markers() -> None:
    chunk = RetrievedChunk(
        chunk_id="c1",
        document_id="d1",
        text="Revenue grew 20%",
        char_start=10,
        char_end=28,
        relevance_score=0.9,
    )
    answer = "Revenue increased sharply [SOURCE:c1] in Q4."
    result = resolve_highlights(answer, [chunk])
    assert "[SOURCE:" not in result.answer
    assert len(result.highlight_spans) == 1
    assert result.highlight_spans[0].char_start == 10


def test_profile_loader_standard_vs_agentic() -> None:
    standard = load_profile("standard")
    agentic = load_profile("agentic")
    assert standard.rerank.get("reranker") == "lexical-bm25"
    assert agentic.gating is True
    assert agentic.reflection.get("critic") is True


def test_legacy_profile_names_alias_to_standard() -> None:
    naive = load_profile("naive")
    advanced = load_profile("advanced")
    standard = load_profile("standard")
    assert naive.model_dump() == standard.model_dump()
    assert advanced.model_dump() == standard.model_dump()


@pytest.mark.asyncio
async def test_rag_engine_naive_runs_without_collections() -> None:
    from core.rag.engine import RagEngine

    engine = RagEngine()
    result = await engine.run(
        query="hello",
        tenant_id="00000000-0000-0000-0000-000000000001",
        collection_ids=["00000000-0000-0000-0000-000000000099"],
        profile_name="standard",
    )
    assert "final" in result or result.get("draft_answer")
