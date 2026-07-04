from unittest.mock import patch

import pytest

import core.ingestion.chunkers.markdown_aware  # noqa: F401
from core.retrieval.qdrant_store import QdrantStore


@pytest.mark.asyncio
async def test_metadata_filter_does_not_exclude_untagged_documents():
    store = QdrantStore()
    col_id = "test-filter-untagged"
    tenant_id = "tenant-filter-1"
    try:
        await store.upsert_chunks(
            col_id,
            tenant_id=tenant_id,
            chunks=[
                {
                    "chunk_id": "doc1:0",
                    "document_id": "doc1",
                    "text": "Retrieval-Augmented Generation combines search with LLM answers.",
                    "char_start": 0,
                    "char_end": 60,
                    "chunk_index": 0,
                    "is_current": True,
                    "version_number": 1,
                    "registry_id": "doc1",
                }
            ],
            embedder_key="hash-dev",
        )
        unfiltered = await store.search(
            col_id,
            query="what is RAG",
            tenant_id=tenant_id,
            embedder_key="hash-dev",
            top_k=5,
            metadata_filter=None,
        )
        filtered = await store.search(
            col_id,
            query="what is RAG",
            tenant_id=tenant_id,
            embedder_key="hash-dev",
            top_k=5,
            metadata_filter={"tags": ["RAG"]},
        )
        assert unfiltered
        assert filtered, "untagged uploads must remain searchable when metadata filters are inferred"
    finally:
        store.delete_collection(col_id)


@pytest.mark.asyncio
async def test_rag_uses_grounded_fallback_when_llm_refuses():
    from sqlalchemy import select

    from core.deps import get_app_sessionmaker
    from core.models import DocumentCollection
    from core.rag.engine import RagEngine

    sessionmaker = get_app_sessionmaker()
    async with sessionmaker() as session:
        col = (await session.execute(select(DocumentCollection).where(DocumentCollection.name == "Test"))).scalar_one_or_none()
        if col is None:
            pytest.skip("Test collection not present in local database")

        class MockLLM:
            async def complete(self, *, system, messages):
                if "metadata filters" in system:
                    return '{"tags": ["RAG"]}'
                return "I cannot find the answer in the provided context."

        with patch("core.llm.factory.LLMProviderFactory.create", return_value=MockLLM()):
            result = await RagEngine().run(
                query="what is RAG?",
                tenant_id=str(col.tenant_id),
                collection_ids=[str(col.id)],
                profile_name=col.rag_profile,
                conversation_history=[],
                db=session,
            )

        final = result.get("final") or {}
        answer = final.get("answer") or ""
        assert not final.get("needs_clarification")
        assert "cannot find the answer" not in answer.lower()
        assert "RAG" in answer.upper()
        assert answer.startswith("##") or "hash" in answer.lower()
        assert "| --- |" not in answer
        assert final.get("highlight_spans") or "[SOURCE:" in answer
