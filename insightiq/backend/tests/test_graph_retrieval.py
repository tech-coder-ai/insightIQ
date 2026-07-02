from __future__ import annotations

from typing import Any

import pytest

from core.graph.entity_extractor import _heuristic_extract, extract_entities
from core.graph.retrieval import graph_retrieve
from core.rag.state import RetrievedChunk


def test_heuristic_extract_finds_capitalized_phrases_and_links_them() -> None:
    text = "Acme Corp announced a partnership with Globex Industries in New York."
    result = _heuristic_extract(text)

    names = {e.name for e in result.entities}
    assert "Acme Corp" in names
    assert "Globex Industries" in names
    assert result.relationships, "expected co-occurrence relationships between entities"
    assert all(r.relation == "co_occurs_with" for r in result.relationships)


def test_heuristic_extract_skips_stopword_only_matches() -> None:
    result = _heuristic_extract("This is a plain sentence with no proper nouns.")
    assert result.entities == []
    assert result.relationships == []


@pytest.mark.asyncio
async def test_extract_entities_returns_empty_for_blank_text() -> None:
    result = await extract_entities("   ")
    assert result.entities == []
    assert result.relationships == []


@pytest.mark.asyncio
async def test_extract_entities_falls_back_to_heuristic_without_llm() -> None:
    # No OPENAI_API_KEY is configured in the test environment, so the LLM
    # call should fail and extraction should degrade to the heuristic path
    # rather than raising.
    text = "Nikola Tesla worked with George Westinghouse on alternating current."
    result = await extract_entities(text)
    names = {e.name for e in result.entities}
    assert names, "expected heuristic fallback to still extract some entities"


class _FakeNeo4jStore:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.calls: list[dict[str, Any]] = []

    async def find_chunks_for_query(
        self, *, tenant_id: str, collection_ids: list[str], query: str, hops: int = 2, limit: int = 10
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {"tenant_id": tenant_id, "collection_ids": collection_ids, "query": query, "hops": hops, "limit": limit}
        )
        return self._rows


@pytest.mark.asyncio
async def test_graph_retrieve_maps_rows_to_retrieved_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"chunk_id": "c1", "document_id": "d1", "text": "Acme reported record revenue.", "char_start": 0, "char_end": 30},
        {"chunk_id": "c2", "document_id": "d1", "text": "Acme partnered with Globex.", "char_start": 31, "char_end": 60},
    ]
    fake_store = _FakeNeo4jStore(rows)
    monkeypatch.setattr("core.graph.retrieval.Neo4jStore", lambda: fake_store)

    results = await graph_retrieve(query="Acme revenue", tenant_id="t1", collection_ids=["col-1"], top_k=5)

    assert len(results) == 2
    assert all(isinstance(c, RetrievedChunk) for c in results)
    assert all(c.retriever_source == "graph" for c in results)
    assert results[0].relevance_score >= results[1].relevance_score
    assert fake_store.calls[0]["query"] == "Acme revenue"
    assert fake_store.calls[0]["hops"] == 2


@pytest.mark.asyncio
async def test_graph_retrieve_returns_empty_when_no_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_store = _FakeNeo4jStore([])
    monkeypatch.setattr("core.graph.retrieval.Neo4jStore", lambda: fake_store)

    results = await graph_retrieve(query="nothing matches", tenant_id="t1", collection_ids=["col-1"])
    assert results == []
