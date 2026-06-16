from __future__ import annotations

import pytest

from core.prompts.judge import judge_output
from core.prompts.renderer import render_template


def test_jinja_render() -> None:
    out = render_template("Hello {{ name }}", {"name": "InsightIQ"})
    assert out == "Hello InsightIQ"


@pytest.mark.asyncio
async def test_judge_returns_scores() -> None:
    scores = await judge_output(prompt="summarize revenue", output="Revenue summary for Q4", expected_keywords=["revenue"])
    assert 0 <= scores.overall <= 1
