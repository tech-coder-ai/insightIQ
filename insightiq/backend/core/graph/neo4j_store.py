from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from config.settings import get_settings_resolver

_driver: AsyncDriver | None = None


def _get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        settings = get_settings_resolver().resolve().neo4j
        _driver = AsyncGraphDatabase.driver(settings.uri, auth=(settings.username, settings.password))
    return _driver


async def close_driver() -> None:
    """Best-effort cleanup hook for app shutdown / tests."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


class Neo4jStore:
    """Thin async wrapper around the Neo4j driver implementing GraphRAG's
    entity/relationship graph (Workstream 2), scoped by `tenant_id`/
    `collection_id` so multiple tenants can safely share one Neo4j instance.

    Schema:
      (:Chunk {chunk_id, tenant_id, collection_id, document_id, text, char_start, char_end})
      (:Entity {name, name_lower, type, tenant_id, collection_id})
      (:Entity)-[:MENTIONED_IN]->(:Chunk)
      (:Entity)-[:RELATES_TO {type}]->(:Entity)
    """

    def __init__(self) -> None:
        self._driver = _get_driver()

    async def upsert_chunk_graph(
        self,
        *,
        tenant_id: str,
        collection_id: str,
        document_id: str,
        chunk_id: str,
        chunk_text: str,
        char_start: int,
        char_end: int,
        entities: list[dict[str, str]],
        relationships: list[dict[str, str]],
    ) -> None:
        if not entities:
            return
        async with self._driver.session() as session:
            await session.execute_write(
                _write_chunk_graph,
                tenant_id=tenant_id,
                collection_id=collection_id,
                document_id=document_id,
                chunk_id=chunk_id,
                chunk_text=chunk_text[:2000],
                char_start=char_start,
                char_end=char_end,
                entities=entities,
                relationships=relationships,
            )

    async def find_chunks_for_query(
        self,
        *,
        tenant_id: str,
        collection_ids: list[str],
        query: str,
        hops: int = 2,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Entity lookup + multi-hop traversal: match entities whose name is
        mentioned in the query, walk up to `hops` RELATES_TO edges to pull in
        connected entities, then return every chunk any of those entities is
        mentioned in."""
        async with self._driver.session() as session:
            return await session.execute_read(
                _read_chunks_for_query,
                tenant_id=tenant_id,
                collection_ids=collection_ids,
                query=query.lower(),
                hops=max(1, min(hops, 3)),
                limit=limit,
            )

    async def entity_count(self, *, tenant_id: str, collection_id: str) -> int:
        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e:Entity {tenant_id: $tenant_id, collection_id: $collection_id}) RETURN count(e) AS n",
                tenant_id=tenant_id,
                collection_id=collection_id,
            )
            row = await result.single()
            return int(row["n"]) if row else 0

    async def delete_collection(self, *, tenant_id: str, collection_id: str) -> None:
        async with self._driver.session() as session:
            await session.run(
                """
                MATCH (n) WHERE n.tenant_id = $tenant_id AND n.collection_id = $collection_id
                DETACH DELETE n
                """,
                tenant_id=tenant_id,
                collection_id=collection_id,
            )


async def _write_chunk_graph(
    tx: Any,
    *,
    tenant_id: str,
    collection_id: str,
    document_id: str,
    chunk_id: str,
    chunk_text: str,
    char_start: int,
    char_end: int,
    entities: list[dict[str, str]],
    relationships: list[dict[str, str]],
) -> None:
    await tx.run(
        """
        MERGE (c:Chunk {chunk_id: $chunk_id, tenant_id: $tenant_id})
        SET c.collection_id = $collection_id, c.document_id = $document_id,
            c.text = $chunk_text, c.char_start = $char_start, c.char_end = $char_end
        """,
        chunk_id=chunk_id,
        tenant_id=tenant_id,
        collection_id=collection_id,
        document_id=document_id,
        chunk_text=chunk_text,
        char_start=char_start,
        char_end=char_end,
    )
    for e in entities:
        name = str(e.get("name", "")).strip()
        if not name:
            continue
        await tx.run(
            """
            MERGE (e:Entity {name_lower: toLower($name), tenant_id: $tenant_id, collection_id: $collection_id})
            ON CREATE SET e.name = $name, e.type = $type
            WITH e
            MATCH (c:Chunk {chunk_id: $chunk_id, tenant_id: $tenant_id})
            MERGE (e)-[:MENTIONED_IN]->(c)
            """,
            name=name,
            type=str(e.get("type", "concept")),
            tenant_id=tenant_id,
            collection_id=collection_id,
            chunk_id=chunk_id,
        )
    for r in relationships:
        source = str(r.get("source", "")).strip()
        target = str(r.get("target", "")).strip()
        relation = str(r.get("relation", "related_to")).strip() or "related_to"
        if not source or not target:
            continue
        await tx.run(
            """
            MERGE (a:Entity {name_lower: toLower($source), tenant_id: $tenant_id, collection_id: $collection_id})
            ON CREATE SET a.name = $source, a.type = 'concept'
            MERGE (b:Entity {name_lower: toLower($target), tenant_id: $tenant_id, collection_id: $collection_id})
            ON CREATE SET b.name = $target, b.type = 'concept'
            MERGE (a)-[rel:RELATES_TO {type: $relation}]->(b)
            """,
            source=source,
            target=target,
            relation=relation,
            tenant_id=tenant_id,
            collection_id=collection_id,
        )


async def _read_chunks_for_query(
    tx: Any,
    *,
    tenant_id: str,
    collection_ids: list[str],
    query: str,
    hops: int,
    limit: int,
) -> list[dict[str, Any]]:
    cypher = f"""
        MATCH (seed:Entity {{tenant_id: $tenant_id}})
        WHERE seed.collection_id IN $collection_ids AND $search_text CONTAINS seed.name_lower
        OPTIONAL MATCH (seed)-[:RELATES_TO*0..{hops}]-(related:Entity)
        WITH collect(DISTINCT seed) + collect(DISTINCT related) AS candidates
        UNWIND candidates AS entity
        WITH DISTINCT entity
        WHERE entity IS NOT NULL
        MATCH (entity)-[:MENTIONED_IN]->(c:Chunk)
        RETURN DISTINCT c.chunk_id AS chunk_id, c.document_id AS document_id, c.text AS text,
               c.char_start AS char_start, c.char_end AS char_end
        LIMIT $limit
    """
    result = await tx.run(cypher, tenant_id=tenant_id, collection_ids=collection_ids, search_text=query, limit=limit)
    return await result.data()
