from __future__ import annotations

from abc import ABC, abstractmethod

from rank_bm25 import BM25Okapi

from core.rag.state import RetrievedChunk
from core.registry import Registry
from core.retrieval.lexical import tokenize

RERANKERS: Registry[IReranker] = Registry("reranker")


class IReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]: ...


@RERANKERS.register("lexical-bm25")
class LexicalBM25Reranker(IReranker):
    """Principle 6 — reranking without a heavy cross-encoder dependency.

    Scores each candidate with real BM25 (computed over the current candidate
    set, which is standard practice for a second-stage reranker) blended with
    query-term coverage and a "does a query term appear early" position
    signal, instead of the previous crude token-overlap ratio.
    """

    _BM25_WEIGHT = 0.65
    _COVERAGE_WEIGHT = 0.25
    _POSITION_WEIGHT = 0.10

    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
        if not chunks:
            return []

        q_tokens = tokenize(query)
        q_set = set(q_tokens)
        tokenized_docs = [tokenize(c.text) for c in chunks]
        bm25_scores = [0.0] * len(chunks)
        if q_tokens and any(tokenized_docs):
            bm25 = BM25Okapi(tokenized_docs)
            bm25_scores = list(bm25.get_scores(q_tokens))
        max_bm25 = max(bm25_scores) if bm25_scores else 0.0

        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk, tokens, bm25_score in zip(chunks, tokenized_docs, bm25_scores, strict=True):
            c_set = set(tokens)
            coverage = (len(q_set & c_set) / len(q_set)) if q_set else 0.0
            position_bonus = 0.0
            if q_set and tokens:
                first_hit = next((i for i, t in enumerate(tokens) if t in q_set), None)
                if first_hit is not None:
                    position_bonus = max(0.0, 1.0 - first_hit / len(tokens))
            normalized_bm25 = (bm25_score / max_bm25) if max_bm25 > 0 else 0.0
            final = (
                self._BM25_WEIGHT * normalized_bm25
                + self._COVERAGE_WEIGHT * coverage
                + self._POSITION_WEIGHT * position_bonus
            )
            scored.append((final, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        ranked: list[RetrievedChunk] = []
        for score, chunk in scored[:top_k]:
            chunk.rerank_score = round(score, 4)
            ranked.append(chunk)
        return ranked


@RERANKERS.register("none")
class NoOpReranker(IReranker):
    async def rerank(self, query: str, chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
        return chunks[:top_k]
