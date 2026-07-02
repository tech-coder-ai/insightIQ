"""Continuous evaluation loop smoke test (RAG principle 10).

Runs a tiny labeled QA set end-to-end through the real RAG engine and scores
each answer with the custom LLM-as-judge module (`core.rag.eval`), replacing
the previous answer-shape-only smoke check. Works without external LLM keys
because `evaluate_answer` degrades to a deterministic lexical heuristic.
"""

from __future__ import annotations

import pytest

from core.rag.eval import EvalCase, run_eval_harness


@pytest.mark.asyncio
async def test_ragas_smoke_golden_query() -> None:
    """Minimal eval gate for CI: pipeline completes, returns an answer, and is scored."""
    reports = await run_eval_harness(
        [EvalCase(question="What is the summary of the annual report?", expected_keywords=["summary"])],
        tenant_id="00000000-0000-0000-0000-000000000001",
        collection_ids=["00000000-0000-0000-0000-000000000099"],
        profile_name="agentic",
    )
    assert len(reports) == 1
    report = reports[0]
    assert isinstance(report.answer, str)
    assert 0.0 <= report.scores.overall <= 1.0
    assert 0.0 <= report.scores.context_precision <= 1.0
    assert 0.0 <= report.scores.faithfulness <= 1.0
    assert 0.0 <= report.scores.answer_relevance <= 1.0
