from __future__ import annotations

import pytest

from core.prompts.bindings import merge_template_variables, resolve_binding_context


def test_merge_template_variables_injects_context() -> None:
    merged = merge_template_variables(
        context_text="row data here",
        context_vars={"sql_result_columns": ["a"]},
        variables={"region": "EMEA"},
    )
    assert merged["context"] == "row data here"
    assert merged["region"] == "EMEA"
    assert merged["sql_result_columns"] == ["a"]


@pytest.mark.asyncio
async def test_none_binding_returns_empty_context() -> None:
    class _Db:
        pass

    text, extra = await resolve_binding_context(_Db(), tenant_id=__import__("uuid").uuid4(), bindings={"type": "none"}, variables={})
    assert text == ""
    assert extra == {}
