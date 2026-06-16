from __future__ import annotations

import re

from core.llm.base import ILLMProvider, LLMMessage
from core.llm.factory import LLM_PROVIDERS

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 1000


@LLM_PROVIDERS.register("heuristic")
class HeuristicLLMProvider(ILLMProvider):
    """
    Phase 1 dev provider: converts a small set of NL patterns to SQL.
    TODO(phase2): replace with Anthropic/OpenAI provider for real NL->SQL.
    """

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        question = messages[-1].content.strip()
        question_lc = question.lower()
        tables = _extract_tables(system)
        limit = _extract_limit(question_lc) or _DEFAULT_LIMIT

        if "count" in question_lc and tables:
            return f"SELECT COUNT(*) AS count FROM {tables[0]}"
        if tables:
            return f"SELECT * FROM {tables[0]} LIMIT {limit}"
        return "SELECT 1 AS value LIMIT 1"


def _extract_tables(system: str) -> list[str]:
    return re.findall(r"table:\s*([a-zA-Z_][a-zA-Z0-9_]*)", system, flags=re.IGNORECASE)


def _extract_limit(question: str) -> int | None:
    """Parse a row limit from phrases like 'top 10', 'first 5 rows', 'limit 20'."""
    patterns = (
        r"\btop\s+(\d+)\b",
        r"\bfirst\s+(\d+)\b",
        r"\blimit\s+(\d+)\b",
        r"\b(\d+)\s+rows?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            value = int(match.group(1))
            return min(max(value, 1), _MAX_LIMIT)
    return None
