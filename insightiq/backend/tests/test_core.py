from __future__ import annotations

import pytest

from core.data.validators.readonly import DESTRUCTIVE, check_readonly_select
from core.llm.base import LLMMessage
from core.llm.heuristic import HeuristicLLMProvider
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


def test_readonly_guard_blocks_mutations() -> None:
    for sql in (
        "DELETE FROM users",
        "UPDATE users SET name = 'x'",
        "INSERT INTO users VALUES (1)",
        "DROP TABLE users",
        "TRUNCATE users",
        "SELECT 1; DROP TABLE users",
    ):
        result = check_readonly_select(sql)
        assert not result.ok, sql

    ok = check_readonly_select("SELECT * FROM users LIMIT 10")
    assert ok.ok


@pytest.mark.asyncio
async def test_heuristic_llm_generates_select() -> None:
    llm = HeuristicLLMProvider()
    sql = await llm.complete(
        system="Available tables:\n- table: users",
        messages=[LLMMessage(role="user", content="show all users")],
    )
    assert sql.upper().startswith("SELECT")
    assert "LIMIT 100" in sql.upper()


@pytest.mark.asyncio
async def test_heuristic_llm_respects_top_n_limit() -> None:
    llm = HeuristicLLMProvider()
    sql = await llm.complete(
        system="Available tables:\n- table: customers",
        messages=[LLMMessage(role="user", content="Show top 10 rows")],
    )
    assert "LIMIT 10" in sql
    assert "LIMIT 100" not in sql
