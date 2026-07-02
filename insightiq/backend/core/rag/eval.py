from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.rag.state import RetrievedChunk
from core.retrieval.lexical import tokenize

_JUDGE_SYSTEM = (
    "You are a strict evaluator of a RAG (retrieval-augmented generation) system. "
    "Given a question, the retrieved context passages, and the generated answer, "
    "score three metrics on a 0.0-1.0 scale:\n"
    "- context_precision: fraction of the retrieved context that is actually relevant "
    "to answering the question.\n"
    "- faithfulness: whether every claim in the answer is directly supported by the "
    "context (no hallucination).\n"
    "- answer_relevance: whether the answer actually addresses the question asked.\n\n"
    "Reply with ONLY compact JSON: "
    '{"context_precision": 0.0, "faithfulness": 0.0, "answer_relevance": 0.0, "reasoning": "..."}'
)


class RagEvalScores(BaseModel):
    context_precision: float = Field(ge=0.0, le=1.0)
    faithfulness: float = Field(ge=0.0, le=1.0)
    answer_relevance: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


async def evaluate_answer(
    *,
    question: str,
    context_chunks: list[RetrievedChunk] | list[str],
    answer: str,
    provider_key: str = "openai",
) -> RagEvalScores:
    """Principle 10 — continuous evaluation loop: a custom, lightweight
    LLM-as-judge scoring Context Precision, Faithfulness, and Answer Relevance
    (the same three RAGAS-style metrics, without the `ragas` package
    dependency). Falls back to a deterministic lexical-overlap heuristic when
    no LLM is configured, so the eval loop always returns a usable signal in
    dev/CI."""
    texts = [c.text if isinstance(c, RetrievedChunk) else str(c) for c in context_chunks]
    context_block = "\n\n".join(f"[{i + 1}] {t}" for i, t in enumerate(texts)) or "(no context retrieved)"

    llm = LLMProviderFactory.create(provider_key)
    try:
        raw = await llm.complete(
            system=_JUDGE_SYSTEM,
            messages=[
                LLMMessage(
                    role="user",
                    content=f"QUESTION:\n{question}\n\nCONTEXT:\n{context_block}\n\nANSWER:\n{answer}",
                )
            ],
        )
        data = _parse_json(raw)
        cp = _clamp(data.get("context_precision"))
        fa = _clamp(data.get("faithfulness"))
        ar = _clamp(data.get("answer_relevance"))
        overall = round((cp + fa + ar) / 3, 3)
        return RagEvalScores(
            context_precision=cp,
            faithfulness=fa,
            answer_relevance=ar,
            overall=overall,
            reasoning=str(data.get("reasoning", ""))[:500],
        )
    except Exception:  # noqa: BLE001 - degrade to heuristic scoring (e.g. no API key in dev)
        return _heuristic_eval(question, texts, answer)


def _clamp(value: object) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        v = 0.0
    return max(0.0, min(1.0, v))


def _parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _heuristic_eval(question: str, context_texts: list[str], answer: str) -> RagEvalScores:
    q_tokens = set(tokenize(question))
    a_tokens = set(tokenize(answer))
    ctx_tokens: set[str] = set()
    for t in context_texts:
        ctx_tokens |= set(tokenize(t))

    context_precision = min(1.0, (len(ctx_tokens & a_tokens) / max(len(ctx_tokens), 1)) * 3) if context_texts else 0.0
    faithfulness = (len(a_tokens & ctx_tokens) / max(len(a_tokens), 1)) if context_texts else 0.4
    answer_relevance = len(q_tokens & a_tokens) / max(len(q_tokens), 1)
    overall = round((context_precision + faithfulness + answer_relevance) / 3, 3)
    return RagEvalScores(
        context_precision=round(context_precision, 3),
        faithfulness=round(min(faithfulness, 1.0), 3),
        answer_relevance=round(min(answer_relevance, 1.0), 3),
        overall=min(overall, 1.0),
        reasoning="heuristic fallback (no LLM available)",
    )


class EvalCase(BaseModel):
    question: str
    expected_keywords: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    case: EvalCase
    answer: str
    scores: RagEvalScores


async def run_eval_harness(
    cases: list[EvalCase],
    *,
    tenant_id: str,
    collection_ids: list[str],
    profile_name: str = "standard",
) -> list[EvalReport]:
    """Runs a small labeled QA set end-to-end through the real RAG engine and
    scores each answer — replaces the smoke-only `tests/eval/ragas_smoke.py`
    with real per-question scoring plus a reusable harness."""
    from core.rag.engine import RagEngine

    engine = RagEngine()
    reports: list[EvalReport] = []
    for case in cases:
        result = await engine.run(
            query=case.question,
            tenant_id=tenant_id,
            collection_ids=collection_ids,
            profile_name=profile_name,
        )
        final = result.get("final") or {}
        answer = final.get("answer", "")
        context_chunks = (result.get("context") or {}).get("chunks", [])
        texts = [c.get("text", "") for c in context_chunks]
        scores = await evaluate_answer(question=case.question, context_chunks=texts, answer=answer)
        reports.append(EvalReport(case=case, answer=answer, scores=scores))
    return reports
