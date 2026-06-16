from __future__ import annotations

import re
from typing import Any

from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.rag.fusion import reciprocal_rank_fusion
from core.rag.highlight_resolver import resolve_highlights
from core.rag.profiles import RagProfileConfig
from core.rag.state import (
    CriticVerdict,
    CuratedContext,
    QueryIntent,
    RetrievalRoute,
    RetrievedChunk,
)
from core.retrieval.qdrant_store import QdrantStore
from core.retrieval.rerankers.heuristic import RERANKERS


def _chunks_from_dict(items: list[dict[str, Any]]) -> list[RetrievedChunk]:
    return [RetrievedChunk(**item) for item in items]


def _chunks_to_dict(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [c.__dict__ for c in chunks]


async def node_understand(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    query = state["raw_query"].strip().lower()
    if cfg.gating and query in {"hi", "hello", "thanks", "thank you"}:
        return {
            "intent": QueryIntent.chit_chat.value,
            "language": "en",
            "needs_retrieval": False,
            "trace": {**state.get("trace", {}), "understand": "gated"},
        }
    intent = QueryIntent.factual.value
    if "summary" in query or "summarize" in query:
        intent = QueryIntent.summary.value
    elif any(w in query for w in ("compare", "versus", "vs")):
        intent = QueryIntent.compare.value
    elif any(w in query for w in ("percent", "ratio", "margin", "revenue")):
        intent = QueryIntent.financial_math.value
    elif " and " in query or " then " in query:
        intent = QueryIntent.multi_hop.value
    return {
        "intent": intent,
        "language": "en",
        "needs_retrieval": True,
        "trace": {**state.get("trace", {}), "understand": intent},
    }


async def node_transform(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    query = state["raw_query"]
    sub_queries = [query]
    variations = [query]
    hyde_doc = None

    if cfg.transform.decompose and " and " in query:
        sub_queries = [p.strip() for p in query.split(" and ") if p.strip()]

    if cfg.transform.variations > 1:
        variations = [query, f"explain {query}", f"details about {query}"][: cfg.transform.variations]

    if cfg.transform.hyde:
        llm = LLMProviderFactory.create("heuristic")
        hyde_doc = await llm.complete(
            system="Write a short hypothetical answer.",
            messages=[LLMMessage(role="user", content=query)],
        )

    rewritten = query
    if cfg.transform.rewrite:
        rewritten = query.rstrip("?") + " (from company documents)"

    return {
        "sub_queries": sub_queries,
        "query_variations": variations,
        "hyde_doc": hyde_doc,
        "raw_query": rewritten,
        "trace": {**state.get("trace", {}), "transform": {"variations": len(variations)}},
    }


async def node_route(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    strategy = cfg.routing.get("strategy", "vector")
    intent = state.get("intent")
    if strategy == "adaptive":
        route = RetrievalRoute.hybrid.value
        if intent == QueryIntent.financial_math.value:
            route = RetrievalRoute.graph.value
    elif strategy == "graph" or intent == QueryIntent.financial_math.value:
        route = RetrievalRoute.graph.value
    elif strategy == "hybrid":
        route = RetrievalRoute.hybrid.value
    else:
        route = RetrievalRoute.vector.value
    return {"route": route, "trace": {**state.get("trace", {}), "route": route}}


async def node_retrieve(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    store = QdrantStore()
    embedder_key = cfg.retrieval.get("embedder", "hash-dev")
    top_k = int(cfg.retrieval.get("top_k", 10))
    tenant_id = state["tenant_id"]
    collection_ids = state["collection_ids"]
    variations = state.get("query_variations") or [state["raw_query"]]
    sub_queries = state.get("sub_queries") or [state["raw_query"]]

    result_sets: list[list[RetrievedChunk]] = []
    for sq in sub_queries:
        for var in variations:
            for collection_id in collection_ids:
                hits = await store.search(
                    collection_id,
                    query=var or sq,
                    tenant_id=tenant_id,
                    embedder_key=embedder_key,
                    top_k=top_k,
                )
                if hits:
                    result_sets.append(hits)

    candidates = result_sets[0] if len(result_sets) == 1 else []
    if len(result_sets) > 1:
        candidates = reciprocal_rank_fusion(result_sets) if cfg.fusion == "rrf" else sum(result_sets, [])

    return {
        "candidates": _chunks_to_dict(candidates),
        "trace": {**state.get("trace", {}), "retrieve": {"sets": len(result_sets), "candidates": len(candidates)}},
    }


async def node_fuse(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    candidates = _chunks_from_dict(state.get("candidates", []))
    if cfg.fusion == "rrf" and candidates:
        fused = reciprocal_rank_fusion([candidates])
    else:
        fused = candidates
    return {"fused": _chunks_to_dict(fused)}


async def node_rerank(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    reranker_key = cfg.rerank.get("reranker", "none")
    top_k = int(cfg.rerank.get("top_k", 5))
    chunks = _chunks_from_dict(state.get("fused") or state.get("candidates", []))
    reranker = RERANKERS.create(reranker_key if reranker_key != "none" else "none")
    reranked = await reranker.rerank(state["raw_query"], chunks, top_k=top_k)
    return {"reranked": _chunks_to_dict(reranked)}


async def node_curate(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    budget = int(cfg.curation.get("token_budget", 4000))
    chunks = _chunks_from_dict(state.get("reranked", []))
    seen: set[str] = set()
    curated: list[RetrievedChunk] = []
    tokens = 0
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        est = len(chunk.text.split())
        if tokens + est > budget:
            break
        curated.append(chunk)
        tokens += est
    return {
        "context": {
            "chunks": _chunks_to_dict(curated),
            "token_estimate": tokens,
        }
    }


async def node_generate(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    query = state["raw_query"]
    if not state.get("needs_retrieval", True):
        llm = LLMProviderFactory.create(cfg.generation.get("llm", "heuristic"))
        answer = await llm.complete(
            system="You are a helpful assistant.",
            messages=[LLMMessage(role="user", content=query)],
        )
        return {"draft_answer": answer}

    context_data = state.get("context") or {}
    chunks = _chunks_from_dict(context_data.get("chunks", []))
    if not chunks:
        return {"draft_answer": "I could not find relevant information in the uploaded documents."}

    if state.get("intent") == QueryIntent.financial_math.value and cfg.generation.get("financial_graph"):
        answer = _financial_answer(query, chunks)
    else:
        parts = []
        for chunk in chunks[:3]:
            parts.append(f"Based on the documents: {chunk.text[:300]} [SOURCE:{chunk.chunk_id}]")
        answer = " ".join(parts)

    return {"draft_answer": answer}


async def node_critic(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    answer = state.get("draft_answer", "")
    chunks = _chunks_from_dict((state.get("context") or {}).get("chunks", []))
    has_source = bool(re.search(r"\[SOURCE:", answer)) or not state.get("needs_retrieval", True)
    groundedness = 1.0 if has_source or not chunks else 0.3
    relevancy = 0.9 if len(answer) > 20 else 0.4
    threshold = float(cfg.rerank.get("min_relevance_threshold", 0.6))
    top_score = chunks[0].rerank_score if chunks and chunks[0].rerank_score else chunks[0].relevance_score if chunks else 0
    pass_ = groundedness >= 0.5 and relevancy >= 0.5 and (not chunks or top_score >= threshold * 0.5)
    verdict = CriticVerdict(
        groundedness=groundedness,
        relevancy=relevancy,
        pass_=pass_,
        missing_info=[] if pass_ else ["insufficient context"],
    )
    return {"critic": verdict.__dict__}


async def node_highlight(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    answer = state.get("draft_answer", "")
    chunks = _chunks_from_dict((state.get("context") or {}).get("chunks", []))
    if cfg.highlight.get("resolve", True) and chunks:
        final = resolve_highlights(answer, chunks)
    else:
        from core.rag.state import HighlightedResponse

        final = HighlightedResponse(answer=answer, answer_html=answer, highlight_spans=[])
    return {"final": final.__dict__}


def _financial_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    try:
        import sympy

        numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", query)]
        if len(numbers) >= 2 and "percent" in query.lower():
            pct = sympy.N(numbers[0] / numbers[1] * 100, 2)
            chunk_id = chunks[0].chunk_id
            return f"The calculated percentage is {pct}%. [SOURCE:{chunk_id}]"
    except Exception:
        pass
    chunk_id = chunks[0].chunk_id
    return f"Financial analysis from documents: {chunks[0].text[:200]} [SOURCE:{chunk_id}]"
