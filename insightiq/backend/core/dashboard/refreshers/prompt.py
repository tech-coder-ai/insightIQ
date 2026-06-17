from __future__ import annotations

from typing import Any

from sqlalchemy import select
import uuid

from core.dashboard.base import CARD_REFRESHERS, ICardRefresher, RefreshResult
from core.deps import get_app_sessionmaker
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.models import PromptTemplate, PromptVersion
from core.prompts.bindings import merge_template_variables, resolve_binding_context
from core.prompts.renderer import render_template
from core.response.types import ResponsePayload, ResponseType


@CARD_REFRESHERS.register("prompt")
class PromptCardRefresher(ICardRefresher):
    async def refresh(self, *, source_config: dict[str, Any], tenant_id: str) -> RefreshResult:
        version_id = uuid.UUID(source_config["version_id"])
        template_id = uuid.UUID(source_config["template_id"])
        variables = source_config.get("variables", {})
        sessionmaker = get_app_sessionmaker()
        async with sessionmaker() as db:
            res = await db.execute(select(PromptVersion).where(PromptVersion.id == version_id))
            version = res.scalar_one_or_none()
            if version is None:
                raise ValueError("prompt version not found")
            tmpl_res = await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.id == template_id,
                    PromptTemplate.tenant_id == uuid.UUID(tenant_id),
                )
            )
            tmpl = tmpl_res.scalar_one_or_none()
            if tmpl is None:
                raise ValueError("prompt template not found")

            context_text, context_vars = await resolve_binding_context(
                db,
                tenant_id=uuid.UUID(tenant_id),
                bindings=tmpl.bindings_json,
                variables=variables,
            )

        merged_variables = merge_template_variables(
            context_text=context_text,
            context_vars=context_vars,
            variables=variables,
        )
        rendered = render_template(version.template_body, merged_variables)
        user_prompt = rendered
        if context_text:
            user_prompt = f"Context:\n{context_text}\n\nTask:\n{rendered}"

        try:
            llm = LLMProviderFactory.create("openai")
        except Exception:  # noqa: BLE001
            llm = LLMProviderFactory.create("heuristic")

        output = await llm.complete(
            system=version.system_prompt or "You are a helpful analyst.",
            messages=[LLMMessage(role="user", content=user_prompt)],
        )
        payload = ResponsePayload(
            response_type=ResponseType.explanation,
            data={"output": output, "rendered_prompt": rendered, "context_preview": context_text[:2000]},
        )
        return RefreshResult(response=payload.model_dump())
