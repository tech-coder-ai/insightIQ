from __future__ import annotations

import pytest

from core.rag.eval import EvalCase, RagEvalScores, _heuristic_eval, evaluate_answer
from core.rag.state import RetrievedChunk


def test_heuristic_eval_scores_are_bounded_and_shaped() -> None:
    scores = _heuristic_eval(
        "What was quarterly revenue?",
        ["Quarterly revenue grew 20% year over year."],
        "Revenue grew 20% in the quarter.",
    )
    assert isinstance(scores, RagEvalScores)
    for value in (scores.context_precision, scores.faithfulness, scores.answer_relevance, scores.overall):
        assert 0.0 <= value <= 1.0
    assert scores.reasoning


def test_heuristic_eval_rewards_answers_grounded_in_context() -> None:
    context = ["Quarterly revenue grew 20% driven by enterprise sales."]
    grounded = _heuristic_eval("What drove revenue growth?", context, "Enterprise sales drove revenue growth of 20%.")
    hallucinated = _heuristic_eval("What drove revenue growth?", context, "The company launched a new mobile app in Tokyo.")
    assert grounded.faithfulness >= hallucinated.faithfulness


def test_heuristic_eval_handles_no_context() -> None:
    scores = _heuristic_eval("What is the answer?", [], "I don't know.")
    assert scores.context_precision == 0.0
    assert 0.0 <= scores.faithfulness <= 1.0


@pytest.mark.asyncio
async def test_evaluate_answer_degrades_to_heuristic_without_llm() -> None:
    # No OPENAI_API_KEY configured in the test environment, so evaluate_answer
    # should catch the LLM failure and fall back to the deterministic scorer.
    chunks = [
        RetrievedChunk(chunk_id="c1", document_id="d1", text="Revenue grew 20% in Q4.", char_start=0, char_end=20),
    ]
    scores = await evaluate_answer(question="How much did revenue grow?", context_chunks=chunks, answer="Revenue grew 20% in Q4.")
    assert isinstance(scores, RagEvalScores)
    assert scores.reasoning == "heuristic fallback (no LLM available)"


@pytest.mark.asyncio
async def test_evaluate_answer_accepts_plain_string_context() -> None:
    scores = await evaluate_answer(
        question="What happened?",
        context_chunks=["Revenue grew 20%."],
        answer="Revenue increased by 20%.",
    )
    assert isinstance(scores, RagEvalScores)


def test_eval_case_defaults_to_empty_keywords() -> None:
    case = EvalCase(question="What is the revenue?")
    assert case.expected_keywords == []
