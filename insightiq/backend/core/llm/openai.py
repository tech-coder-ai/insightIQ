from __future__ import annotations

import os

from core.llm.base import ILLMProvider, LLMMessage
from core.llm.factory import LLM_PROVIDERS


@LLM_PROVIDERS.register("openai")
class OpenAILLMProvider(ILLMProvider):
    """Chat-completions provider.

    Configuration is read from the environment so credentials never live in
    code, and so OpenAI-compatible endpoints (Groq, Together, vLLM, LM Studio,
    Azure-style gateways, …) work by only changing env vars:

    - ``OPENAI_API_KEY``  (required)
    - ``OPENAI_BASE_URL`` (optional; point at any OpenAI-compatible endpoint)
    - ``OPENAI_MODEL``    (optional; defaults to ``gpt-4o-mini``)

    Note: this module is named ``openai`` to match the provider key used by the
    factory (``core.llm.<key>``). ``from openai import ...`` below resolves to
    the installed top-level package (absolute import), not this module.
    """

    def __init__(self, *, model: str | None = None) -> None:
        self._api_key = os.getenv("OPENAI_API_KEY")
        self._base_url = os.getenv("OPENAI_BASE_URL") or None
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it (and optionally OPENAI_MODEL / "
                "OPENAI_BASE_URL) to enable LLM-generated answers."
            )

        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        payload = [{"role": "system", "content": system}]
        payload.extend({"role": m.role, "content": m.content} for m in messages)
        resp = await client.chat.completions.create(
            model=self._model,
            messages=payload,  # type: ignore[arg-type]
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()
