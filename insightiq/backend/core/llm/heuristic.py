from __future__ import annotations

import re

from core.llm.base import ILLMProvider, LLMMessage
from core.llm.factory import LLM_PROVIDERS


@LLM_PROVIDERS.register("heuristic")
class HeuristicLLMProvider(ILLMProvider):
    """
    Phase 1 dev provider: converts a small set of NL patterns to SQL.
    TODO(phase2): replace with Anthropic/OpenAI provider for real NL->SQL.
    """

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        question = messages[-1].content.strip().lower()
        tables = _extract_tables(system)

        if "count" in question and tables:
            return f"SELECT COUNT(*) AS count FROM {tables[0]} LIMIT 100"
        if tables:
            return f"SELECT * FROM {tables[0]} LIMIT 100"
        return "SELECT 1 AS value LIMIT 1"


def _extract_tables(system: str) -> list[str]:
    return re.findall(r"table:\s*([a-zA-Z_][a-zA-Z0-9_]*)", system, flags=re.IGNORECASE)
