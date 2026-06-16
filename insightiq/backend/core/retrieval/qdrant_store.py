from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from config.settings import get_settings_resolver
from core.embeddings.factory import EmbedderFactory
from core.rag.state import RetrievedChunk


class QdrantStore:
    def __init__(self) -> None:
        settings = get_settings_resolver().resolve()
        self._client = QdrantClient(url=settings.qdrant.url)

    def ensure_collection(self, name: str, *, dimension: int, embedding_model: str) -> None:
        if self._client.collection_exists(name):
            info = self._client.get_collection(name)
            existing = info.config.params.vectors  # type: ignore[union-attr]
            if isinstance(existing, dict):
                return
        self._client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
        )

    async def upsert_chunks(
        self,
        collection_name: str,
        *,
        tenant_id: str,
        chunks: list[dict[str, Any]],
        embedder_key: str,
    ) -> None:
        embedder = EmbedderFactory.create(embedder_key)
        self.ensure_collection(collection_name, dimension=embedder.dimension, embedding_model=embedder.model_name)
        texts = [c["text"] for c in chunks]
        vectors = await embedder.embed_texts(texts)
        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid4())
            chunk["qdrant_point_id"] = point_id
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "chunk_id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "tenant_id": tenant_id,
                        "collection_id": collection_name,
                        "text": chunk["text"],
                        "char_start": chunk["char_start"],
                        "char_end": chunk["char_end"],
                        "page_number": chunk.get("page_number"),
                        "embedding_model": embedder.model_name,
                    },
                )
            )
        self._client.upsert(collection_name=collection_name, points=points)

    async def search(
        self,
        collection_name: str,
        *,
        query: str,
        tenant_id: str,
        embedder_key: str,
        top_k: int = 10,
    ) -> list[RetrievedChunk]:
        embedder = EmbedderFactory.create(embedder_key)
        vector = (await embedder.embed_texts([query]))[0]
        results = self._client.search(
            collection_name=collection_name,
            query_vector=vector,
            limit=top_k,
            query_filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id))]
            ),
        )
        chunks: list[RetrievedChunk] = []
        for hit in results:
            p = hit.payload or {}
            chunks.append(
                RetrievedChunk(
                    chunk_id=str(p.get("chunk_id", "")),
                    document_id=str(p.get("document_id", "")),
                    text=str(p.get("text", "")),
                    char_start=int(p.get("char_start", 0)),
                    char_end=int(p.get("char_end", 0)),
                    page_number=p.get("page_number"),
                    relevance_score=float(hit.score or 0.0),
                    retriever_source="dense",
                )
            )
        return chunks
