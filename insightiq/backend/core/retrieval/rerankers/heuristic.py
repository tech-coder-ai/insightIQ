from __future__ import annotations

from abc import ABC, abstractmethod

from core.rag.state import RetrievedChunk
from core.registry import Registry

RERANKERS: Registry[IReranker] = Registry("reranker")


class IReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]: ...


@RERANKERS.register("cross-encoder-heuristic")
class HeuristicReranker(IReranker):
    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
        q_tokens = set(query.lower().split())

        def score(chunk: RetrievedChunk) -> float:
            c_tokens = set(chunk.text.lower().split())
            overlap = len(q_tokens & c_tokens)
            return overlap / max(len(q_tokens), 1)

        ranked = sorted(chunks, key=score, reverse=True)[:top_k]
        for c in ranked:
            c.rerank_score = score(c)
        return ranked


@RERANKERS.register("none")
class NoOpReranker(IReranker):
    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
        return chunks[:top_k]
