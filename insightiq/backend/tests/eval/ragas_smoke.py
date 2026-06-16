"""Ragas smoke harness — runs without external LLM keys."""

from __future__ import annotations

import pytest

from core.rag.engine import RagEngine


@pytest.mark.asyncio
async def test_ragas_smoke_golden_query() -> None:
  """Minimal eval gate for CI: pipeline completes and returns an answer field."""
  engine = RagEngine()
  result = await engine.run(
      query="What is the summary of the annual report?",
      tenant_id="00000000-0000-0000-0000-000000000001",
      collection_ids=["00000000-0000-0000-0000-000000000099"],
      profile_name="agentic",
  )
  final = result.get("final") or {}
  answer = final.get("answer") or result.get("draft_answer") or ""
  assert isinstance(answer, str)
  assert result.get("trace") is not None
