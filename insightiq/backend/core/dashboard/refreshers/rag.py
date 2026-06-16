from __future__ import annotations

from typing import Any

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher, RefreshResult
from core.rag.engine import RagEngine
from core.response.types import ResponsePayload


@CARD_REFRESHERS.register("rag")
class RagCardRefresher(ICardRefresher):
    async def refresh(self, *, source_config: dict[str, Any], tenant_id: str) -> RefreshResult:
        collection_id = source_config["collection_id"]
        question = source_config["question"]
        snapshot = source_config.get("rag_profile_snapshot") or {}
        profile = snapshot.get("profile") or source_config.get("rag_profile", "naive")
        engine = RagEngine()
        result = await engine.run(
            query=question,
            tenant_id=tenant_id,
            collection_ids=[collection_id],
            profile_name=profile,
        )
        final = result.get("final") or {}
        payload = ResponsePayload(
            response_type="explanation",
            title=question,
            data={
                "answer": final.get("answer", ""),
                "answer_html": final.get("answer_html", ""),
                "highlight_spans": final.get("highlight_spans", []),
            },
        )
        return RefreshResult(response=payload.model_dump())
