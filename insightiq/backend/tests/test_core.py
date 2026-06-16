from __future__ import annotations

import pytest

from core.data.validators.postgres_validator import DESTRUCTIVE
from core.llm.heuristic import HeuristicLLMProvider
from core.llm.base import LLMMessage
from core.registry import Registry, UnknownPluginError


def test_registry_register_and_create() -> None:
    reg: Registry[str] = Registry("test")

    @reg.register("a")
    class A:
        def __init__(self, *, value: str) -> None:
            self.value = value

    created = reg.create("a", value="ok")
    assert created.value == "ok"

    with pytest.raises(UnknownPluginError):
        reg.create("missing")


def test_destructive_sql_pattern() -> None:
    assert DESTRUCTIVE.search("DELETE FROM users")
    assert not DESTRUCTIVE.search("SELECT * FROM users")


@pytest.mark.asyncio
async def test_heuristic_llm_generates_select() -> None:
    llm = HeuristicLLMProvider()
    sql = await llm.complete(
        system="Available tables:\n- table: users",
        messages=[LLMMessage(role="user", content="show all users")],
    )
    assert sql.upper().startswith("SELECT")
