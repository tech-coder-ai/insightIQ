from __future__ import annotations

from core.rag.graph_builder import build_graph
from core.rag.profiles import load_profile, to_rag_profile
from core.rag.state import Message


class RagEngine:
    async def run(
        self,
        *,
        query: str,
        tenant_id: str,
        collection_ids: list[str],
        profile_name: str = "naive",
        conversation_history: list[Message] | None = None,
        system_prompt_override: str | None = None,
        generation_instructions: str | None = None,
    ) -> dict:
        cfg = load_profile(profile_name)
        graph = build_graph(cfg)
        initial = {
            "raw_query": query,
            "conversation_history": [
                {"role": m.role, "content": m.content} for m in (conversation_history or [])
            ],
            "collection_ids": collection_ids,
            "tenant_id": tenant_id,
            "profile": to_rag_profile(cfg).raw,
            "retrieval_round": 0,
            "trace": {},
            "system_prompt_override": system_prompt_override,
            "generation_instructions": generation_instructions,
        }
        return await graph.ainvoke(initial)
