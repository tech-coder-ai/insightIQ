from __future__ import annotations

from core.rag.state import RetrievedChunk


def reciprocal_rank_fusion(result_sets: list[list[RetrievedChunk]], *, k: int = 60) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    best: dict[str, RetrievedChunk] = {}
    for result_set in result_sets:
        for rank, chunk in enumerate(result_set, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            best[chunk.chunk_id] = chunk
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    fused: list[RetrievedChunk] = []
    for chunk_id, score in ordered:
        chunk = best[chunk_id]
        chunk.relevance_score = score
        fused.append(chunk)
    return fused
