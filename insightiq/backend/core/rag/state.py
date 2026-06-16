from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypedDict


class QueryIntent(StrEnum):
    factual = "factual"
    summary = "summary"
    compare = "compare"
    financial_math = "financial_math"
    multi_hop = "multi_hop"
    chit_chat = "chit_chat"


class RetrievalRoute(StrEnum):
    vector = "vector"
    hybrid = "hybrid"
    graph = "graph"
    sql_over_docs = "sql_over_docs"


@dataclass
class Message:
    role: str
    content: str


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    char_start: int
    char_end: int
    page_number: int | None = None
    relevance_score: float = 0.0
    rerank_score: float | None = None
    retriever_source: str = "dense"


@dataclass
class CuratedContext:
    chunks: list[RetrievedChunk]
    token_estimate: int = 0


@dataclass
class CriticVerdict:
    groundedness: float
    relevancy: float
    pass_: bool
    missing_info: list[str] = field(default_factory=list)


@dataclass
class HighlightSpan:
    chunk_id: str
    document_id: str
    char_start: int
    char_end: int
    page_number: int | None
    color: str
    relevance_score: float
    rerank_score: float | None = None


@dataclass
class HighlightedResponse:
    answer: str
    answer_html: str
    highlight_spans: list[HighlightSpan]
    response_type: str = "explanation"


@dataclass
class RagProfile:
    profile: str
    raw: dict[str, Any]


class RagGraphState(TypedDict, total=False):
    """LangGraph state schema.

    Every key must be declared so that values supplied in the initial input
    (e.g. ``tenant_id``, ``collection_ids``) are kept as channels and persist
    across nodes. ``total=False`` lets nodes return partial updates.
    """

    raw_query: str
    conversation_history: list[dict[str, Any]]
    collection_ids: list[str]
    tenant_id: str
    profile: dict[str, Any]
    intent: str | None
    language: str | None
    needs_retrieval: bool
    sub_queries: list[str]
    query_variations: list[str]
    hyde_doc: str | None
    route: str | None
    candidates: list[Any]
    fused: list[Any]
    reranked: list[Any]
    context: Any
    draft_answer: str | None
    critic: Any
    retrieval_round: int
    final: Any
    trace: dict[str, Any]


@dataclass
class RagState:
    raw_query: str
    conversation_history: list[Message]
    collection_ids: list[str]
    tenant_id: str
    profile: RagProfile

    intent: QueryIntent | None = None
    language: str | None = None
    needs_retrieval: bool = True
    sub_queries: list[str] = field(default_factory=list)
    query_variations: list[str] = field(default_factory=list)
    hyde_doc: str | None = None

    route: RetrievalRoute | None = None
    candidates: list[RetrievedChunk] = field(default_factory=list)
    fused: list[RetrievedChunk] = field(default_factory=list)
    reranked: list[RetrievedChunk] = field(default_factory=list)
    context: CuratedContext | None = None

    draft_answer: str | None = None
    critic: CriticVerdict | None = None
    retrieval_round: int = 0
    final: HighlightedResponse | None = None
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "conversation_history": [{"role": m.role, "content": m.content} for m in self.conversation_history],
            "collection_ids": self.collection_ids,
            "tenant_id": self.tenant_id,
            "profile": self.profile.raw,
            "intent": self.intent.value if self.intent else None,
            "language": self.language,
            "needs_retrieval": self.needs_retrieval,
            "sub_queries": self.sub_queries,
            "query_variations": self.query_variations,
            "hyde_doc": self.hyde_doc,
            "route": self.route.value if self.route else None,
            "candidates": [c.__dict__ for c in self.candidates],
            "fused": [c.__dict__ for c in self.fused],
            "reranked": [c.__dict__ for c in self.reranked],
            "context": {"chunks": [c.__dict__ for c in self.context.chunks], "token_estimate": self.context.token_estimate}
            if self.context
            else None,
            "draft_answer": self.draft_answer,
            "critic": self.critic.__dict__ if self.critic else None,
            "retrieval_round": self.retrieval_round,
            "final": self.final.__dict__ if self.final else None,
            "trace": self.trace,
        }
