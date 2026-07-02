from __future__ import annotations

from core.data.connectors.base import QueryResult, ValidationResult
from core.data.schema import ColumnMeta, SchemaMetadata, TableMeta
from core.llm.base import LLMMessage
from core.llm.heuristic import HeuristicLLMProvider
from services.talk_to_data import api as t2d


def _pagila_like_schema() -> SchemaMetadata:
    return SchemaMetadata(
        tables=[
            TableMeta(
                name="actor",
                columns=[
                    ColumnMeta(name="actor_id", data_type="integer", is_primary_key=True),
                    ColumnMeta(name="first_name", data_type="varchar"),
                    ColumnMeta(name="last_name", data_type="varchar"),
                ],
            ),
            TableMeta(
                name="film",
                columns=[
                    ColumnMeta(name="film_id", data_type="integer", is_primary_key=True),
                    ColumnMeta(name="title", data_type="varchar"),
                    ColumnMeta(name="rental_rate", data_type="numeric"),
                ],
            ),
            TableMeta(
                name="rental",
                columns=[
                    ColumnMeta(name="rental_id", data_type="integer", is_primary_key=True),
                    ColumnMeta(name="inventory_id", data_type="integer"),
                    ColumnMeta(name="customer_id", data_type="integer"),
                ],
            ),
            TableMeta(
                name="film_actor",
                columns=[
                    ColumnMeta(name="actor_id", data_type="integer"),
                    ColumnMeta(name="film_id", data_type="integer"),
                ],
            ),
        ]
    )


def _system_prompt(schema: SchemaMetadata) -> str:
    return t2d._build_sql_system_prompt("postgres", schema, [], [], question="most rented film")


class FakeConnector:
    def __init__(self, *, validate_ok: bool = True) -> None:
        self._validate_ok = validate_ok
        self.executed: list[str] = []

    async def test_connection(self) -> bool:
        return True

    async def introspect_schema(self) -> SchemaMetadata:
        return SchemaMetadata()

    async def execute_query(self, sql: str) -> QueryResult:
        self.executed.append(sql)
        return QueryResult(columns=["x"], rows=[[1]])

    async def validate_sql(self, sql: str) -> ValidationResult:
        return ValidationResult(ok=self._validate_ok)


# --- HeuristicLLMProvider: table matching should prefer relevant tables over the first one ---


async def test_heuristic_picks_relevant_table_not_first_table() -> None:
    schema = _pagila_like_schema()
    system = _system_prompt(schema)
    provider = HeuristicLLMProvider()

    raw = await provider.complete(system=system, messages=[LLMMessage(role="user", content="show me all rentals")])

    assert "rental" in raw.lower()
    assert "actor" not in raw.lower()


async def test_heuristic_orders_by_numeric_column_for_superlative_question() -> None:
    schema = _pagila_like_schema()
    system = _system_prompt(schema)
    provider = HeuristicLLMProvider()

    raw = await provider.complete(
        system=system, messages=[LLMMessage(role="user", content="which film has the highest rental_rate")]
    )

    assert "film" in raw.lower()
    assert "order by" in raw.lower()
    assert "desc" in raw.lower()


async def test_heuristic_handles_count_questions() -> None:
    schema = _pagila_like_schema()
    system = _system_prompt(schema)
    provider = HeuristicLLMProvider()

    raw = await provider.complete(system=system, messages=[LLMMessage(role="user", content="how many rentals are there")])

    assert raw.upper().startswith("SELECT COUNT(*)")
    assert "rental" in raw.lower()


async def test_heuristic_parses_row_limits() -> None:
    schema = _pagila_like_schema()
    system = _system_prompt(schema)
    provider = HeuristicLLMProvider()

    raw = await provider.complete(system=system, messages=[LLMMessage(role="user", content="show top 5 actors")])

    assert "limit 5" in raw.lower()


# --- Confidence-driven judging: without an LLM, never blindly trust the heuristic guess ---


async def test_judge_sql_without_llm_returns_low_confidence_and_tip() -> None:
    schema = _pagila_like_schema()

    judged = await t2d._judge_sql(
        dialect="postgres",
        schema=schema,
        question="most rented film",
        sql="SELECT * FROM actor LIMIT 100",
        llm_generated=False,
    )

    assert judged.confidence < t2d._CONFIDENCE_CLARIFY
    assert judged.clarifying_question
    assert judged.suggested_rephrase


async def test_judge_sql_llm_generated_defaults_to_high_confidence_when_judge_unavailable() -> None:
    # No OPENAI_API_KEY is configured in the test environment, so the judging call
    # itself fails — but since the SQL came from a real LLM generation pass, we
    # should still trust it rather than forcing an unnecessary confirmation.
    schema = _pagila_like_schema()

    judged = await t2d._judge_sql(
        dialect="postgres",
        schema=schema,
        question="list all films",
        sql="SELECT * FROM film LIMIT 100",
        llm_generated=True,
    )

    assert judged.confidence >= t2d._CONFIDENCE_AUTO_RUN


# --- End-to-end resolution: heuristic-mode should ask for clarification, not run garbage SQL ---


async def test_resolve_sql_or_clarify_asks_for_clarification_without_llm() -> None:
    schema = _pagila_like_schema()
    system_prompt = t2d._build_sql_system_prompt("postgres", schema, [], [], question="most rented film")
    connector = FakeConnector()

    resolution = await t2d._resolve_sql_or_clarify(
        dialect="postgres",
        schema=schema,
        system_prompt=system_prompt,
        question="most rented film",
        connector=connector,
    )

    # No OPENAI_API_KEY in the test env => heuristic generation => low confidence,
    # so the resolver must not silently hand back a (likely wrong) query to run.
    assert resolution.sql is None
    assert connector.executed == []
    if resolution.clarification:
        assert "tip" in resolution.clarification.lower() or "?" in resolution.clarification
    elif resolution.proposal:
        assert resolution.proposal.sql


class _FakeOpenAI:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        return self._responses.pop(0)


def _patch_openai(monkeypatch, responses: list[str]) -> None:
    fake = _FakeOpenAI(responses)
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake if key == "openai" else HeuristicLLMProvider())


async def test_resolve_sql_or_clarify_runs_directly_when_llm_is_confident(monkeypatch) -> None:
    schema = _pagila_like_schema()
    system_prompt = t2d._build_sql_system_prompt("postgres", schema, [], [], question="list actors")
    connector = FakeConnector()

    _patch_openai(
        monkeypatch,
        [
            "SELECT * FROM actor LIMIT 100",
            '{"confidence": 0.95, "sql": "SELECT * FROM actor LIMIT 100", '
            '"interpretation": "List actors", "clarifying_question": null, "suggested_rephrase": null}',
        ],
    )

    resolution = await t2d._resolve_sql_or_clarify(
        dialect="postgres",
        schema=schema,
        system_prompt=system_prompt,
        question="list actors",
        connector=connector,
    )

    assert resolution.sql == "SELECT * FROM actor LIMIT 100"
    assert resolution.proposal is None
    assert resolution.clarification is None


async def test_resolve_sql_or_clarify_proposes_confirmation_when_llm_is_unsure(monkeypatch) -> None:
    schema = _pagila_like_schema()
    system_prompt = t2d._build_sql_system_prompt("postgres", schema, [], [], question="most rented film")
    connector = FakeConnector()

    _patch_openai(
        monkeypatch,
        [
            "SELECT film_id, COUNT(*) AS rentals FROM rental GROUP BY film_id ORDER BY rentals DESC LIMIT 1",
            '{"confidence": 0.55, '
            '"sql": "SELECT film_id, COUNT(*) AS rentals FROM rental GROUP BY film_id ORDER BY rentals DESC LIMIT 1", '
            '"interpretation": "Film with the most rentals, by rental count", "clarifying_question": null, '
            '"suggested_rephrase": "Show the film with the highest number of rentals, including its title"}',
        ],
    )

    resolution = await t2d._resolve_sql_or_clarify(
        dialect="postgres",
        schema=schema,
        system_prompt=system_prompt,
        question="most rented film",
        connector=connector,
    )

    assert resolution.sql is None
    assert resolution.proposal is not None
    assert "rentals DESC" in resolution.proposal.sql
    assert resolution.proposal.suggested_rephrase
    assert connector.executed == []


class _CapturingOpenAI:
    """Fake provider that records the messages it was called with, for asserting context flow."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[LLMMessage]] = []

    async def complete(self, *, system: str, messages: list[LLMMessage]) -> str:
        self.calls.append(list(messages))
        return self._responses.pop(0)


def _history_with_prior_result() -> list[LLMMessage]:
    return [
        LLMMessage(role="user", content="most rented film"),
        LLMMessage(
            role="assistant",
            content=(
                "SQL executed:\n"
                "SELECT f.title, COUNT(*) AS rentals FROM film f JOIN inventory i ON i.film_id=f.film_id "
                "JOIN rental r ON r.inventory_id=i.inventory_id GROUP BY f.title ORDER BY rentals DESC LIMIT 1\n\n"
                "Result:\ntitle | rentals\n-----+-------\nACADEMY DINOSAUR | 32"
            ),
        ),
    ]


async def test_resolve_sql_or_clarify_forwards_history_to_generation(monkeypatch) -> None:
    """The chat context (including the prior turn's actual result) must reach the LLM so a
    follow-up like 'tell me the cast for this film' can resolve 'this film' correctly."""
    schema = _pagila_like_schema()
    system_prompt = t2d._build_sql_system_prompt("postgres", schema, [], [], question="tell me the cast for this film")
    connector = FakeConnector()
    history = _history_with_prior_result()

    fake = _CapturingOpenAI(
        [
            "SELECT a.first_name, a.last_name FROM actor a "
            "JOIN film_actor fa ON fa.actor_id = a.actor_id "
            "JOIN film f ON f.film_id = fa.film_id WHERE f.title = 'ACADEMY DINOSAUR'",
            '{"confidence": 0.9, "sql": null, "interpretation": "Cast of ACADEMY DINOSAUR", '
            '"clarifying_question": null, "suggested_rephrase": null}',
        ]
    )
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake if key == "openai" else HeuristicLLMProvider())

    resolution = await t2d._resolve_sql_or_clarify(
        dialect="postgres",
        schema=schema,
        system_prompt=system_prompt,
        question="tell me the cast for this film",
        connector=connector,
        prior_messages=history,
    )

    assert resolution.sql is not None
    assert "ACADEMY DINOSAUR" in resolution.sql
    # Both the generation call and the judging call must have seen the prior result.
    for call_messages in fake.calls:
        combined = " ".join(m.content for m in call_messages)
        assert "ACADEMY DINOSAUR" in combined


async def test_maybe_answer_from_context_returns_none_without_history() -> None:
    schema = _pagila_like_schema()
    result = await t2d._maybe_answer_from_context(question="what tables are there", history=[], schema=schema)
    assert result is None


async def test_maybe_answer_from_context_uses_llm_when_available(monkeypatch) -> None:
    schema = _pagila_like_schema()
    history = _history_with_prior_result()
    fake = _CapturingOpenAI(['{"answer": "The most rented film was ACADEMY DINOSAUR, with 32 rentals."}'])
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake)

    result = await t2d._maybe_answer_from_context(
        question="how many rentals did it have again?", history=history, schema=schema
    )

    assert result is not None
    assert "32" in result
    assert "ACADEMY DINOSAUR" in fake.calls[0][-2].content or "ACADEMY DINOSAUR" in fake.calls[0][0].content


async def test_maybe_answer_from_context_falls_through_when_llm_says_new_query_needed(monkeypatch) -> None:
    schema = _pagila_like_schema()
    history = _history_with_prior_result()
    fake = _CapturingOpenAI(['{"answer": null}'])
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake)

    result = await t2d._maybe_answer_from_context(
        question="tell me the cast for this film", history=history, schema=schema
    )

    assert result is None


def test_smalltalk_reply_matches_gratitude_without_touching_sql() -> None:
    assert t2d._smalltalk_reply("thanks") is not None
    assert t2d._smalltalk_reply("Thank you!") is not None
    assert t2d._smalltalk_reply("thanks a lot.") is not None


def test_smalltalk_reply_matches_greetings_and_farewells() -> None:
    assert t2d._smalltalk_reply("hi") is not None
    assert t2d._smalltalk_reply("Hello!") is not None
    assert t2d._smalltalk_reply("bye") is not None
    assert t2d._smalltalk_reply("goodbye!") is not None


def test_smalltalk_reply_does_not_match_data_questions() -> None:
    assert t2d._smalltalk_reply("most rented film") is None
    assert t2d._smalltalk_reply("tell me the cast for this film") is None
    assert t2d._smalltalk_reply("how many customers do we have") is None


def test_smalltalk_patterns_never_collide_with_confirm_or_reject_vocabulary() -> None:
    """'thanks' must never be swallowed as a yes/no on a pending SQL proposal, and vice versa."""
    for kind, pattern in t2d._SMALLTALK_PATTERNS.items():
        for affirmative_word in ("yes", "ok", "okay", "sure", "confirm", "confirmed", "go ahead", "proceed"):
            assert not pattern.match(affirmative_word), f"{kind!r} pattern collides with {affirmative_word!r}"
        for negative_word in ("no", "cancel", "wrong", "try again"):
            assert not pattern.match(negative_word), f"{kind!r} pattern collides with {negative_word!r}"
    for _smalltalk_kind, phrases in (
        ("thanks", ["thanks", "thank you"]),
        ("greeting", ["hi", "hello"]),
        ("farewell", ["bye", "goodbye"]),
    ):
        for phrase in phrases:
            assert not t2d._is_affirmative(phrase), f"{phrase!r} should not be treated as a confirmation"
            assert not t2d._is_negative(phrase), f"{phrase!r} should not be treated as a rejection"


async def test_classify_message_intent_falls_back_to_regex_without_llm() -> None:
    # No OPENAI_API_KEY in the test environment, so this exercises the offline fallback.
    assert await t2d._classify_message_intent("yes", has_pending_proposal=True) == "confirm"
    assert await t2d._classify_message_intent("no", has_pending_proposal=True) == "reject"
    assert await t2d._classify_message_intent("thanks", has_pending_proposal=False) == "smalltalk"
    assert await t2d._classify_message_intent("most rented film", has_pending_proposal=False) == "data_question"


async def test_classify_message_intent_uses_llm_when_available(monkeypatch) -> None:
    fake = _CapturingOpenAI(['{"intent": "smalltalk"}'])
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake)

    intent = await t2d._classify_message_intent("thanks so much, appreciate the help!", has_pending_proposal=False)

    assert intent == "smalltalk"
    assert len(fake.calls) == 1


async def test_classify_message_intent_ignores_invalid_llm_output(monkeypatch) -> None:
    # A malformed/garbage LLM response should fall back to the regex heuristic rather than
    # crash or silently misclassify.
    fake = _CapturingOpenAI(['{"intent": "not_a_real_category"}'])
    monkeypatch.setattr(t2d.LLMProviderFactory, "create", lambda key, **kw: fake)

    intent = await t2d._classify_message_intent("most rented film", has_pending_proposal=False)

    assert intent == "data_question"


def test_proposal_message_includes_suggested_rephrase_tip() -> None:
    proposal = t2d.SqlProposal(
        interpretation="Count of rentals per film",
        sql="SELECT film_id, COUNT(*) FROM rental GROUP BY film_id",
        suggested_rephrase="Show the top 5 most rented films",
    )

    message = t2d._proposal_message(proposal)

    assert "Tip" in message
    assert "top 5 most rented films" in message
