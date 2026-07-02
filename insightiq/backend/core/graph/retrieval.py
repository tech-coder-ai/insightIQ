from __future__ import annotations

from core.graph.neo4j_store import Neo4jStore
from core.rag.state import RetrievedChunk


async def graph_retrieve(
    *, query: str, tenant_id: str, collection_ids: list[str], top_k: int = 10
) -> list[RetrievedChunk]:
    """GraphRAG multi-hop retrieval (Workstream 2): match entities mentioned in
    the query against the tenant's Neo4j entity graph, traverse up to 2 hops of
    RELATES_TO edges, and return the chunks connected to that neighborhood.
    Called from `core.rag.nodes._graph_retrieve` and merged with vector/BM25
    results via the same RRF fusion used for hybrid search."""
    store = Neo4jStore()
    rows = await store.find_chunks_for_query(
        tenant_id=tenant_id,
        collection_ids=collection_ids,
        query=query,
        hops=2,
        limit=top_k,
    )
    chunks: list[RetrievedChunk] = []
    for i, row in enumerate(rows):
        chunks.append(
            RetrievedChunk(
                chunk_id=str(row.get("chunk_id", "")),
                document_id=str(row.get("document_id", "")),
                text=str(row.get("text", "")),
                char_start=int(row.get("char_start") or 0),
                char_end=int(row.get("char_end") or 0),
                relevance_score=max(0.1, 1.0 - i * 0.05),
                retriever_source="graph",
            )
        )
    return chunks
