from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from config.settings import get_settings_resolver
from core.embeddings.factory import EmbedderFactory
from core.rag.state import RetrievedChunk


def _chunk_from_payload(p: dict[str, Any], *, score: float = 0.0, source: str = "dense") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(p.get("chunk_id", "")),
        document_id=str(p.get("document_id", "")),
        text=str(p.get("text", "")),
        char_start=int(p.get("char_start", 0)),
        char_end=int(p.get("char_end", 0)),
        page_number=p.get("page_number"),
        relevance_score=score,
        retriever_source=source,
        parent_char_start=p.get("parent_char_start"),
        parent_char_end=p.get("parent_char_end"),
        document_type=p.get("document_type"),
        tags=list(p.get("tags") or []),
    )


class QdrantStore:
    _UPSERT_BATCH_SIZE = 64

    def __init__(self) -> None:
        settings = get_settings_resolver().resolve()
        self._batch_size = max(1, settings.qdrant.upsert_batch_size)
        self._client = QdrantClient(
            url=settings.qdrant.url,
            timeout=settings.qdrant.timeout_seconds,
            check_compatibility=False,
        )

    def delete_collection(self, name: str) -> None:
        if self._client.collection_exists(name):
            self._client.delete_collection(collection_name=name)

    def delete_document_points(self, collection_name: str, *, document_id: str) -> None:
        if not self._client.collection_exists(collection_name):
            return
        self._client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id))]
                )
            ),
        )

    def ensure_collection(self, name: str, *, dimension: int, embedding_model: str) -> None:
        if self._client.collection_exists(name):
            return
        try:
            self._client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
            )
        except Exception:  # noqa: BLE001 - tolerate a concurrent create (409 already exists)
            if not self._client.collection_exists(name):
                raise

    async def upsert_chunks(
        self,
        collection_name: str,
        *,
        tenant_id: str,
        chunks: list[dict[str, Any]],
        embedder_key: str,
    ) -> None:
        if not chunks:
            return
        embedder = EmbedderFactory.create(embedder_key)
        self.ensure_collection(collection_name, dimension=embedder.dimension, embedding_model=embedder.model_name)
        batch_size = self._batch_size
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            texts = [c["text"] for c in batch]
            vectors = await embedder.embed_texts(texts)
            points = []
            for chunk, vector in zip(batch, vectors, strict=True):
                point_id = str(uuid.uuid4())
                chunk["qdrant_point_id"] = point_id
                payload: dict[str, Any] = {
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "tenant_id": tenant_id,
                    "collection_id": collection_name,
                    "text": chunk["text"],
                    "char_start": chunk["char_start"],
                    "char_end": chunk["char_end"],
                    "page_number": chunk.get("page_number"),
                    "embedding_model": embedder.model_name,
                    "parent_char_start": chunk.get("parent_char_start"),
                    "parent_char_end": chunk.get("parent_char_end"),
                    "is_current": bool(chunk.get("is_current", True)),
                    "version_number": int(chunk.get("version_number", 1)),
                    "registry_id": str(chunk.get("registry_id", chunk["document_id"])),
                }
                if chunk.get("document_type"):
                    payload["document_type"] = chunk["document_type"]
                if chunk.get("tags"):
                    payload["tags"] = list(chunk["tags"])
                points.append(qmodels.PointStruct(id=point_id, vector=vector, payload=payload))
            self._client.upsert(collection_name=collection_name, points=points)

    def _build_filter(self, tenant_id: str, metadata_filter: dict[str, Any] | None) -> qmodels.Filter:
        current_only = qmodels.Filter(
            should=[
                qmodels.FieldCondition(key="is_current", match=qmodels.MatchValue(value=True)),
                qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="is_current")),
            ]
        )
        must: list[Any] = [
            qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id)),
            current_only,
        ]
        if metadata_filter:
            document_type = metadata_filter.get("document_type")
            if document_type:
                # Documents uploaded without an explicit type should still be searchable.
                must.append(
                    qmodels.Filter(
                        should=[
                            qmodels.FieldCondition(
                                key="document_type",
                                match=qmodels.MatchValue(value=document_type),
                            ),
                            qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="document_type")),
                        ]
                    )
                )
            tags = metadata_filter.get("tags")
            if tags:
                must.append(
                    qmodels.Filter(
                        should=[
                            qmodels.FieldCondition(
                                key="tags",
                                match=qmodels.MatchAny(any=list(tags)),
                            ),
                            qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="tags")),
                        ]
                    )
                )
        return qmodels.Filter(must=must)

    async def search(
        self,
        collection_name: str,
        *,
        query: str,
        tenant_id: str,
        embedder_key: str,
        top_k: int = 10,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        embedder = EmbedderFactory.create(embedder_key)
        vector = (await embedder.embed_texts([query]))[0]
        if not self._client.collection_exists(collection_name):
            return []
        response = self._client.query_points(
            collection_name=collection_name,
            query=vector,
            limit=top_k,
            with_payload=True,
            query_filter=self._build_filter(tenant_id, metadata_filter),
        )
        return [_chunk_from_payload(hit.payload or {}, score=float(hit.score or 0.0)) for hit in response.points]

    async def scroll_all(
        self,
        collection_name: str,
        *,
        tenant_id: str,
        metadata_filter: dict[str, Any] | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fetch every chunk payload in a collection (bounded by `limit`) for
        building an in-memory BM25 sparse index (principle 4 — hybrid search),
        without needing a separate keyword-search datastore."""
        if not self._client.collection_exists(collection_name):
            return []
        payloads: list[dict[str, Any]] = []
        next_offset = None
        query_filter = self._build_filter(tenant_id, metadata_filter)
        while len(payloads) < limit:
            batch, next_offset = self._client.scroll(
                collection_name=collection_name,
                scroll_filter=query_filter,
                with_payload=True,
                with_vectors=False,
                limit=min(256, limit - len(payloads)),
                offset=next_offset,
            )
            payloads.extend(p.payload or {} for p in batch)
            if next_offset is None:
                break
        return payloads
