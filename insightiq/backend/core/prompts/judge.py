from __future__ import annotations

from pydantic import BaseModel, Field


class EvalScores(BaseModel):
    faithfulness: float = Field(ge=0.0, le=1.0)
    relevancy: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    notes: str = ""


async def judge_output(*, prompt: str, output: str, expected_keywords: list[str] | None = None) -> EvalScores:
    """
    Phase 5 heuristic LLM-as-judge.
    TODO(phase6): replace with real judge model via ILLMProvider.
    """
    keywords = expected_keywords or []
    text = output.lower()
    faithfulness = 0.85 if len(output) > 20 else 0.4
    relevancy = 0.9 if any(k.lower() in text for k in keywords) or not keywords else 0.55
    if any(w in prompt.lower() for w in ("summarize", "summary")) and "summary" not in text:
        relevancy = min(relevancy, 0.6)
    overall = round((faithfulness + relevancy) / 2, 2)
    return EvalScores(
        faithfulness=faithfulness,
        relevancy=relevancy,
        overall=overall,
        notes="heuristic judge (dev)",
    )
