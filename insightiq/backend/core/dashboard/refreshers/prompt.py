from __future__ import annotations

from typing import Any

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher, RefreshResult
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.prompts.renderer import render_template
from core.response.types import ResponsePayload, ResponseType
from sqlalchemy import select
from core.deps import get_app_sessionmaker
from core.models import PromptVersion
import uuid


@CARD_REFRESHERS.register("prompt")
class PromptCardRefresher(ICardRefresher):
    async def refresh(self, *, source_config: dict[str, Any], tenant_id: str) -> RefreshResult:
        version_id = uuid.UUID(source_config["version_id"])
        variables = source_config.get("variables", {})
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as db:
            res = await db.execute(select(PromptVersion).where(PromptVersion.id == version_id))
            version = res.scalar_one_or_none()
            if version is None:
                raise ValueError("prompt version not found")

        rendered = render_template(version.template_body, variables)
        llm = LLMProviderFactory.create("heuristic")
        output = await llm.complete(
            system=version.system_prompt or "You are a helpful analyst.",
            messages=[LLMMessage(role="user", content=rendered)],
        )
        payload = ResponsePayload(
            response_type=ResponseType.explanation,
            data={"output": output, "rendered_prompt": rendered},
        )
        return RefreshResult(response=payload.model_dump())
