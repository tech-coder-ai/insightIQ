from __future__ import annotations

from pydantic import BaseModel, Field

from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory


class EvalScores(BaseModel):
    faithfulness: float = Field(ge=0.0, le=1.0)
    relevancy: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    notes: str = ""


async def judge_output(*, prompt: str, output: str, expected_keywords: list[str] | None = None) -> EvalScores:
    """LLM-as-judge using the heuristic provider for dev; swap provider via config in production."""
    llm = LLMProviderFactory.create("heuristic")
    review = await llm.complete(
        system="Grade the answer 0-1 for faithfulness and relevancy. Reply JSON only.",
        messages=[
            LLMMessage(
                role="user",
                content=f"PROMPT:\n{prompt}\n\nOUTPUT:\n{output}\n\nKEYWORDS:{expected_keywords or []}",
            )
        ],
    )
    keywords = expected_keywords or []
    text = output.lower()
    faithfulness = 0.85 if len(output) > 20 else 0.4
    relevancy = 0.9 if any(k.lower() in text for k in keywords) or not keywords else 0.55
    if "faithfulness" in review.lower():
        faithfulness = min(0.95, faithfulness + 0.05)
    overall = round((faithfulness + relevancy) / 2, 2)
    return EvalScores(
        faithfulness=faithfulness,
        relevancy=relevancy,
        overall=overall,
        notes=f"heuristic judge (dev); review={review[:80]}",
    )
