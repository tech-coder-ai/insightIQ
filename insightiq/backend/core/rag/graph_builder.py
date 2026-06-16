from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from core.rag.nodes import (
    node_critic,
    node_curate,
    node_fuse,
    node_generate,
    node_highlight,
    node_rerank,
    node_retrieve,
    node_route,
    node_transform,
    node_understand,
)
from core.rag.profiles import RagProfileConfig
from core.rag.state import RagGraphState


def build_graph(cfg: RagProfileConfig):
    graph = StateGraph(RagGraphState)

    async def understand(s: dict[str, Any]) -> dict[str, Any]:
        return await node_understand(s, cfg)

    async def transform(s: dict[str, Any]) -> dict[str, Any]:
        return await node_transform(s, cfg)

    async def route(s: dict[str, Any]) -> dict[str, Any]:
        return await node_route(s, cfg)

    async def retrieve(s: dict[str, Any]) -> dict[str, Any]:
        return await node_retrieve(s, cfg)

    async def fuse(s: dict[str, Any]) -> dict[str, Any]:
        return await node_fuse(s, cfg)

    async def rerank(s: dict[str, Any]) -> dict[str, Any]:
        return await node_rerank(s, cfg)

    async def curate(s: dict[str, Any]) -> dict[str, Any]:
        return await node_curate(s, cfg)

    async def generate(s: dict[str, Any]) -> dict[str, Any]:
        return await node_generate(s, cfg)

    async def critic(s: dict[str, Any]) -> dict[str, Any]:
        return await node_critic(s, cfg)

    async def highlight(s: dict[str, Any]) -> dict[str, Any]:
        return await node_highlight(s, cfg)

    async def prepare_retry(s: dict[str, Any]) -> dict[str, Any]:
        return {"retrieval_round": int(s.get("retrieval_round", 0)) + 1}

    graph.add_node("understand", understand)
    graph.add_node("transform", transform)
    graph.add_node("route", route)
    graph.add_node("retrieve", retrieve)
    graph.add_node("fuse", fuse)
    graph.add_node("rerank", rerank)
    graph.add_node("curate", curate)
    graph.add_node("generate", generate)
    graph.add_node("critic", critic)
    graph.add_node("highlight", highlight)
    graph.add_node("prepare_retry", prepare_retry)

    graph.add_edge(START, "understand")

    def after_understand(state: dict[str, Any]) -> str:
        if not state.get("needs_retrieval", True):
            return "generate"
        if (
            cfg.transform.rewrite
            or cfg.transform.decompose
            or cfg.transform.variations > 1
            or cfg.transform.hyde
        ):
            return "transform"
        return "route"

    graph.add_conditional_edges(
        "understand",
        after_understand,
        {"transform": "transform", "route": "route", "generate": "generate"},
    )
    graph.add_edge("transform", "route")
    graph.add_edge("route", "retrieve")

    if cfg.fusion == "rrf":
        graph.add_edge("retrieve", "fuse")
        graph.add_edge("fuse", "rerank")
    else:
        graph.add_edge("retrieve", "rerank")

    graph.add_edge("rerank", "curate")
    graph.add_edge("curate", "generate")

    use_critic = bool(cfg.reflection.get("critic"))

    if use_critic:
        graph.add_edge("generate", "critic")
        max_rounds = int(cfg.reflection.get("max_corrective_rounds", 0))

        def after_critic(state: dict[str, Any]) -> str:
            critic_result = state.get("critic") or {}
            if not critic_result.get("pass_") and state.get("retrieval_round", 0) < max_rounds:
                return "retry"
            return "highlight"

        graph.add_conditional_edges("critic", after_critic, {"retry": "prepare_retry", "highlight": "highlight"})
        graph.add_edge("prepare_retry", "retrieve")
    else:
        graph.add_edge("generate", "highlight")

    graph.add_edge("highlight", END)
    return graph.compile()
