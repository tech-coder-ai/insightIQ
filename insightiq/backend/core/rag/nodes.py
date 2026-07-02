from __future__ import annotations

import json
import re
from typing import Any

from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.rag.context import hydrate_parent_context
from core.rag.fusion import reciprocal_rank_fusion
from core.rag.highlight_resolver import resolve_highlights
from core.rag.profiles import RagProfileConfig
from core.rag.state import (
    CriticVerdict,
    HighlightedResponse,
    QueryIntent,
    RetrievalRoute,
    RetrievedChunk,
)
from core.retrieval.bm25_index import BM25Index
from core.retrieval.lexical import tokenize
from core.retrieval.qdrant_store import QdrantStore
from core.retrieval.rerankers.heuristic import RERANKERS


def _chunks_from_dict(items: list[dict[str, Any]]) -> list[RetrievedChunk]:
    return [RetrievedChunk(**item) for item in items]


def _chunks_to_dict(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [c.__dict__ for c in chunks]


def _history_llm_messages(state: dict[str, Any]) -> list[LLMMessage]:
    messages: list[LLMMessage] = []
    for item in state.get("conversation_history") or []:
        role = item.get("role", "user")
        content = (item.get("content") or "").strip()
        if content and role in {"user", "assistant", "system"}:
            messages.append(LLMMessage(role=role, content=content))
    return messages


def _extract_json_object(raw: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_json_array(raw: str) -> list[Any]:
    match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def _standalone_query(
    query: str,
    history: list[LLMMessage],
    *,
    provider_key: str,
) -> str:
    if not history:
        return query
    llm = LLMProviderFactory.create(provider_key)
    system = (
        "Given a conversation and a follow-up question, rewrite the follow-up as a "
        "standalone question that preserves necessary context from prior turns. "
        "Output only the rewritten question."
    )
    messages = list(history[-10:])
    messages.append(LLMMessage(role="user", content=query))
    try:
        rewritten = await llm.complete(system=system, messages=messages)
        return rewritten.strip() or query
    except Exception:  # noqa: BLE001 - LLM may be unavailable (no API key in dev)
        return query


async def _decompose_query(query: str, provider_key: str) -> list[str]:
    """Principle 3 (part 1) — real LLM-based sub-query decomposition, replacing
    the previous naive `" and "` string split."""
    llm = LLMProviderFactory.create(provider_key)
    system = (
        "Decompose the user's question into 1-4 focused, standalone sub-questions "
        "needed to fully answer it. Reply with ONLY a JSON array of strings, e.g. "
        '["sub-question 1", "sub-question 2"]. If the question is already atomic, '
        "reply with a single-element array containing the original question."
    )
    try:
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=query)])
        sub_qs = [str(s).strip() for s in _extract_json_array(raw) if str(s).strip()]
        return sub_qs[:4] or [query]
    except Exception:  # noqa: BLE001 - fall back to a naive heuristic split
        if re.search(r"\band\b", query, flags=re.IGNORECASE):
            parts = [p.strip() for p in re.split(r"\band\b", query, flags=re.IGNORECASE) if p.strip()]
            return parts or [query]
        return [query]


async def _generate_hyde(query: str, provider_key: str) -> str | None:
    """Principle 3 (part 2) — HyDE: generate a hypothetical answer passage that
    is embedded and searched in `node_retrieve` (previously generated then
    discarded)."""
    llm = LLMProviderFactory.create(provider_key)
    try:
        doc = await llm.complete(
            system=(
                "Write a short, plausible hypothetical passage (3-5 sentences) that "
                "would answer the user's question, as if extracted from a company "
                "document. This is used only to improve semantic search recall "
                "(HyDE) and is never shown to the user."
            ),
            messages=[LLMMessage(role="user", content=query)],
        )
        return doc.strip() or None
    except Exception:  # noqa: BLE001 - HyDE is best-effort
        return None


async def _extract_metadata_filter(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any] | None:
    """Principle 5 — LLM-extracted metadata filters (document_type / tags)
    applied to both Qdrant and the BM25 index at retrieval time."""
    if not cfg.retrieval.get("metadata_filtering"):
        return None
    query = state.get("raw_query", "")
    provider_key = cfg.generation.get("llm", "heuristic")
    llm = LLMProviderFactory.create(provider_key)
    system = (
        "Extract optional metadata filters implied by the user's question about a "
        "document collection. Valid fields: document_type (a short category like "
        "'contract', 'report', 'policy', 'invoice') and tags (a list of topical "
        'keywords). Reply with ONLY compact JSON, e.g. {"document_type": "contract", '
        '"tags": ["renewal"]}. If no filter is clearly implied, reply with {}.'
    )
    try:
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=query)])
        data = _extract_json_object(raw)
        filt: dict[str, Any] = {}
        doc_type = data.get("document_type")
        if isinstance(doc_type, str) and doc_type.strip():
            filt["document_type"] = doc_type.strip()
        tags = data.get("tags")
        if isinstance(tags, list):
            clean_tags = [str(t).strip() for t in tags if str(t).strip()]
            if clean_tags:
                filt["tags"] = clean_tags
        return filt or None
    except Exception:  # noqa: BLE001 - metadata filtering is a pure optimization
        return None


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
    history = _history_llm_messages(state)
    provider_key = cfg.generation.get("llm", "heuristic")
    search_query = query
    if history:
        search_query = await _standalone_query(query, history, provider_key=provider_key)

    sub_queries = [search_query]
    if cfg.transform.decompose:
        sub_queries = await _decompose_query(search_query, provider_key)

    variations = [search_query]
    if cfg.transform.variations > 1:
        variations = [
            search_query,
            f"explain {search_query}",
            f"details about {search_query}",
        ][: cfg.transform.variations]

    hyde_doc = None
    if cfg.transform.hyde:
        hyde_doc = await _generate_hyde(search_query, provider_key)

    rewritten = search_query
    if cfg.transform.rewrite:
        rewritten = search_query.rstrip("?") + " (from company documents)"

    return {
        "sub_queries": sub_queries,
        "query_variations": variations,
        "hyde_doc": hyde_doc,
        "raw_query": rewritten,
        "trace": {
            **state.get("trace", {}),
            "transform": {"variations": len(variations), "sub_queries": len(sub_queries), "hyde": bool(hyde_doc)},
        },
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


async def _graph_retrieve(state: dict[str, Any], cfg: RagProfileConfig) -> list[RetrievedChunk]:
    """Seam for Workstream 2 (Neo4j GraphRAG). Degrades to no results — and
    therefore pure vector/BM25 retrieval — until `core.graph` is configured
    and reachable, so this never breaks profiles that opt into the graph
    route before Neo4j is wired up."""
    try:
        from core.graph.retrieval import graph_retrieve
    except Exception:  # noqa: BLE001 - core.graph / neo4j driver not available
        return []
    try:
        return await graph_retrieve(
            query=state.get("raw_query", ""),
            tenant_id=state["tenant_id"],
            collection_ids=state["collection_ids"],
            top_k=int(cfg.retrieval.get("top_k", 10)),
        )
    except Exception:  # noqa: BLE001 - Neo4j unreachable/misconfigured; degrade gracefully
        return []


async def node_retrieve(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    store = QdrantStore()
    embedder_key = cfg.retrieval.get("embedder", "hash-dev")
    top_k = int(cfg.retrieval.get("top_k", 10))
    tenant_id = state["tenant_id"]
    collection_ids = state["collection_ids"]
    retriever_mode = cfg.retrieval.get("retriever", "vector")
    route = state.get("route")
    variations = state.get("query_variations") or [state["raw_query"]]
    sub_queries = state.get("sub_queries") or [state["raw_query"]]
    hyde_doc = state.get("hyde_doc")

    metadata_filter = await _extract_metadata_filter(state, cfg)

    search_terms: list[str] = []
    seen_terms: set[str] = set()
    for sq in sub_queries:
        for var in variations:
            term = (var or sq or "").strip()
            if term and term not in seen_terms:
                seen_terms.add(term)
                search_terms.append(term)
    # Principle 3 — HyDE: the hypothetical document is embedded and searched
    # like any other query variation instead of being generated and discarded.
    if hyde_doc and hyde_doc.strip() and hyde_doc.strip() not in seen_terms:
        search_terms.append(hyde_doc.strip())

    use_sparse = retriever_mode == "hybrid" or route == RetrievalRoute.hybrid.value
    bm25 = BM25Index(store) if use_sparse else None

    result_sets: list[list[RetrievedChunk]] = []
    for term in search_terms:
        for collection_id in collection_ids:
            dense_hits = await store.search(
                collection_id,
                query=term,
                tenant_id=tenant_id,
                embedder_key=embedder_key,
                top_k=top_k,
                metadata_filter=metadata_filter,
            )
            if dense_hits:
                result_sets.append(dense_hits)
            if bm25 is not None:
                # Principle 4 — hybrid dense + sparse (BM25) search, fused via RRF below.
                sparse_hits = await bm25.search(
                    collection_id, term, tenant_id=tenant_id, top_k=top_k, metadata_filter=metadata_filter
                )
                if sparse_hits:
                    result_sets.append(sparse_hits)

    graph_hits: list[RetrievedChunk] = []
    if route == RetrievalRoute.graph.value:
        graph_hits = await _graph_retrieve(state, cfg)
        if graph_hits:
            result_sets.append(graph_hits)

    if not result_sets:
        candidates: list[RetrievedChunk] = []
    elif len(result_sets) == 1:
        candidates = result_sets[0]
    else:
        candidates = reciprocal_rank_fusion(result_sets) if cfg.fusion == "rrf" else sum(result_sets, [])

    return {
        "candidates": _chunks_to_dict(candidates),
        "trace": {
            **state.get("trace", {}),
            "retrieve": {
                "sets": len(result_sets),
                "candidates": len(candidates),
                "sparse": bm25 is not None,
                "metadata_filter": metadata_filter,
                "graph_hits": len(graph_hits),
            },
        },
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


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _compress_text(text: str, query: str, *, max_sentences: int = 12, min_sentences: int = 2) -> str:
    """Principle 7 — context compression & pruning: score each sentence against
    the query (term overlap, position, presence of figures) and drop
    low-signal/boilerplate sentences instead of feeding the entire (possibly
    parent-expanded) passage to the LLM."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if len(sentences) <= min_sentences:
        return text

    q_tokens = {t for t in tokenize(query) if len(t) > 2}
    scored: list[tuple[float, int]] = []
    for i, sentence in enumerate(sentences):
        s_tokens = set(tokenize(sentence))
        overlap = len(q_tokens & s_tokens)
        position_bonus = 0.2 if i == 0 else 0.0  # keep topic/lead sentences
        has_number = 0.1 if re.search(r"\d", sentence) else 0.0
        length_penalty = -0.1 if len(sentence) < 15 else 0.0  # drop short boilerplate fragments
        scored.append((overlap + position_bonus + has_number + length_penalty, i))

    keep_count = max(min_sentences, min(max_sentences, len(sentences)))
    top_indices = sorted(i for _, i in sorted(scored, reverse=True)[:keep_count])
    return " ".join(sentences[i] for i in top_indices)


async def node_curate(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    budget = int(cfg.curation.get("token_budget", 4000))
    chunks = _chunks_from_dict(state.get("reranked", []))

    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        unique.append(chunk)

    try:
        # Principle 2 — parent-child chunking: hydrate the small, precise
        # child chunk into its larger enclosing section before compression
        # and generation, while keeping char_start/char_end precise for
        # citations/highlighting.
        await hydrate_parent_context(unique, state.get("db"))
    except Exception:  # noqa: BLE001 - parent hydration is best-effort
        pass

    query = state.get("raw_query", "")
    if cfg.curation.get("compress"):
        for c in unique:
            c.context_text = _compress_text(c.context_text or c.text, query)

    curated: list[RetrievedChunk] = []
    tokens = 0
    for chunk in unique:
        text_for_budget = chunk.context_text or chunk.text
        est = len(text_for_budget.split())
        if curated and tokens + est > budget:
            break
        curated.append(chunk)
        tokens += est

    return {
        "context": {
            "chunks": _chunks_to_dict(curated),
            "token_estimate": tokens,
        }
    }


_GROUNDED_SYSTEM = (
    'You are InsightIQ\'s document assistant. Answer the user\'s question using ONLY the '
    'information inside the <doc id="..."> context passages below — never rely on prior '
    "knowledge, and never invent facts not present in the passages.\n\n"
    "Formatting requirements — respond in GitHub-Flavoured Markdown and make it "
    "presentable:\n"
    "- Use headings, **bold** labels, and bullet or numbered lists to structure the answer.\n"
    "- When comparing items or listing attributes, use a Markdown table.\n"
    "- For processes, relationships, hierarchies or flows, include a Mermaid diagram in a "
    "```mermaid code block (e.g. `flowchart TD` or `graph LR`).\n"
    "- Use fenced code blocks for code or config.\n\n"
    "Citations — after each sentence or bullet that uses a passage, append a citation in "
    "the exact form [SOURCE:<doc id>] using that passage's id (place them at the end of "
    "sentences/list items, never inside a table cell or code block). If several passages "
    "support a point, cite each.\n\n"
    "If the context does not contain the answer, reply with exactly: \"I cannot find the "
    'answer in the provided context." Do not guess, speculate, or fall back on general '
    "knowledge."
)


def _build_context_block(chunks: list[RetrievedChunk], limit: int) -> str:
    blocks = []
    for c in chunks[:limit]:
        text = c.context_text or c.text
        blocks.append(f'<doc id="{c.chunk_id}">\n{text}\n</doc>')
    return "\n\n".join(blocks)


def _extractive_fallback(chunks: list[RetrievedChunk], reason: str) -> str:
    top = chunks[0]
    snippet = (top.context_text or top.text)[:500].strip()
    return (
        f"\u26a0\ufe0f The language model is not available right now ({reason}), so here is the "
        f"most relevant passage I found:\n\n{snippet} [SOURCE:{top.chunk_id}]"
    )


async def node_generate(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    query = state["raw_query"]
    provider_key = cfg.generation.get("llm", "heuristic")
    history = _history_llm_messages(state)

    if not state.get("needs_retrieval", True):
        llm = LLMProviderFactory.create(provider_key)
        try:
            answer = await llm.complete(
                system="You are InsightIQ, a helpful and concise assistant.",
                messages=[*history, LLMMessage(role="user", content=query)],
            )
        except Exception as exc:  # noqa: BLE001 - surface a friendly message instead of 500
            answer = f"\u26a0\ufe0f The language model is not available right now ({exc})."
        return {"draft_answer": answer}

    context_data = state.get("context") or {}
    chunks = _chunks_from_dict(context_data.get("chunks", []))
    if not chunks:
        return {"draft_answer": "I cannot find the answer in the provided context."}

    if (
        state.get("intent") == QueryIntent.financial_math.value
        and cfg.generation.get("financial_graph")
        and any(c.retriever_source == "graph" for c in chunks)
    ):
        return {"draft_answer": _financial_answer(query, chunks)}

    max_chunks = int(cfg.generation.get("max_context_chunks", 6))
    context_block = _build_context_block(chunks, max_chunks)
    instructions = state.get("generation_instructions") or ""
    user_prompt = f"Context passages:\n\n{context_block}\n\nQuestion: {query}"
    if instructions.strip():
        user_prompt += f"\n\nAdditional instructions:\n{instructions.strip()}"

    system_prompt = state.get("system_prompt_override") or _GROUNDED_SYSTEM
    llm = LLMProviderFactory.create(provider_key)
    try:
        answer = await llm.complete(
            system=system_prompt,
            messages=[*history, LLMMessage(role="user", content=user_prompt)],
        )
        if not answer.strip():
            answer = _extractive_fallback(chunks, "empty response")
    except Exception as exc:  # noqa: BLE001 - keep the chat responsive, surface the reason
        answer = _extractive_fallback(chunks, str(exc))

    if "[SOURCE:" not in answer and "cannot find the answer" not in answer.lower():
        answer = f"{answer} [SOURCE:{chunks[0].chunk_id}]"

    return {"draft_answer": answer}


async def node_critic(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    """Principle 8 — corrective/agentic RAG: also computes a `confidence`
    score surfaced on the API response and used to decide whether to trigger
    a clarifying question after corrective retries are exhausted."""
    answer = state.get("draft_answer", "")
    chunks = _chunks_from_dict((state.get("context") or {}).get("chunks", []))
    has_source = bool(re.search(r"\[SOURCE:", answer)) or not state.get("needs_retrieval", True)
    no_answer = "cannot find the answer" in answer.lower()
    groundedness = 1.0 if has_source or not chunks else 0.3
    relevancy = 0.4 if (len(answer) <= 20 or no_answer) else 0.9
    threshold = float(cfg.rerank.get("min_relevance_threshold", 0.6))
    top_score = (chunks[0].rerank_score or chunks[0].relevance_score) if chunks else 0.0
    pass_ = (
        not no_answer
        and groundedness >= 0.5
        and relevancy >= 0.5
        and (not chunks or top_score >= threshold * 0.5)
    )
    confidence = (
        round(groundedness * 0.5 + relevancy * 0.3 + min(max(top_score, 0.0), 1.0) * 0.2, 3)
        if chunks
        else round(groundedness * 0.5 + relevancy * 0.5, 3)
    )
    verdict = CriticVerdict(
        groundedness=groundedness,
        relevancy=relevancy,
        pass_=pass_,
        confidence=confidence,
        missing_info=[] if pass_ else ["insufficient context"],
    )
    return {"critic": verdict.__dict__}


async def node_clarify(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    """Principle 8 — when confidence stays low after exhausting corrective
    retries, ask a clarifying question instead of returning a weak/guessed
    answer."""
    query = state["raw_query"]
    provider_key = cfg.generation.get("llm", "heuristic")
    llm = LLMProviderFactory.create(provider_key)
    try:
        question = await llm.complete(
            system=(
                "The retrieved documents were not confident enough to answer the "
                "user's question. Ask ONE short, specific clarifying question that "
                "would help narrow down what they are looking for (e.g. a date "
                "range, document name, or more specific term). Reply with only the "
                "question, no preamble."
            ),
            messages=[LLMMessage(role="user", content=query)],
        )
        question = question.strip() or "Could you clarify or narrow down your question?"
    except Exception:  # noqa: BLE001 - LLM may be unavailable; use a generic prompt
        question = (
            "I couldn't find a confident answer in the documents. Could you rephrase "
            "your question, or specify a document, date range, or topic?"
        )
    return {
        "draft_answer": question,
        "needs_clarification": True,
        "clarifying_question": question,
    }


async def node_highlight(state: dict[str, Any], cfg: RagProfileConfig) -> dict[str, Any]:
    answer = state.get("draft_answer", "")
    chunks = _chunks_from_dict((state.get("context") or {}).get("chunks", []))
    critic = state.get("critic") or {}

    if state.get("needs_clarification"):
        final = HighlightedResponse(answer=answer, answer_html=answer, highlight_spans=[], response_type="clarification")
    elif cfg.highlight.get("resolve", True) and chunks:
        final = resolve_highlights(answer, chunks)
    else:
        final = HighlightedResponse(answer=answer, answer_html=answer, highlight_spans=[])

    default_confidence = 1.0 if not state.get("needs_retrieval", True) else (0.75 if chunks else 0.2)
    return {
        "final": {
            "answer": final.answer,
            "answer_html": final.answer_html,
            "highlight_spans": [h.__dict__ for h in final.highlight_spans],
            "response_type": final.response_type,
            "confidence": critic.get("confidence", default_confidence),
            "needs_clarification": bool(state.get("needs_clarification", False)),
            "clarifying_question": state.get("clarifying_question"),
        }
    }


def _financial_answer(query: str, chunks: list[RetrievedChunk]) -> str:
    """Graph-grounded generation (Workstream 2): synthesizes a deterministic
    answer directly from the graph-sourced passages, with SymPy used only for
    simple arithmetic the user explicitly asked for (e.g. a percentage of two
    numbers already in the question) — replacing the old context-free
    SymPy/regex stub with output actually grounded in the traversed graph."""
    graph_chunks = [c for c in chunks if c.retriever_source == "graph"] or chunks
    try:
        import sympy

        numbers = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", query)]
        if len(numbers) >= 2 and "percent" in query.lower():
            pct = sympy.N(numbers[0] / numbers[1] * 100, 2)
            return f"The calculated percentage is {pct}%. [SOURCE:{graph_chunks[0].chunk_id}]"
    except Exception:
        pass

    lines = ["Based on the knowledge graph built from your documents:"]
    for c in graph_chunks[:3]:
        text = (c.context_text or c.text).strip().replace("\n", " ")
        snippet = text[:220] + ("..." if len(text) > 220 else "")
        lines.append(f"- {snippet} [SOURCE:{c.chunk_id}]")
    return "\n".join(lines)
