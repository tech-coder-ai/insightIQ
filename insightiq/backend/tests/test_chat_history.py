from __future__ import annotations

import uuid

from core.chat_history import _assistant_content, chat_message_to_llm
from core.models import ChatMessage


def test_assistant_content_prefers_response_output() -> None:
    msg = ChatMessage(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="SELECT 1",
        metadata_json={
            "sql": "SELECT count(*) FROM film",
            "response": {"data": {"output": "There are 1000 films."}},
        },
    )
    llm = chat_message_to_llm(msg)
    assert llm.role == "assistant"
    assert "SELECT count(*) FROM film" in llm.content
    assert "1000 films" in llm.content
    assert _assistant_content(msg) == llm.content


def test_assistant_content_includes_table_result_rows() -> None:
    """Follow-up questions ('tell me the cast for this film') need the actual returned
    entity, not just the SQL — otherwise the LLM has no way to resolve 'this film'."""
    msg = ChatMessage(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="",
        metadata_json={
            "sql": "SELECT f.title, COUNT(*) AS rentals FROM film f "
            "JOIN inventory i ON i.film_id = f.film_id "
            "JOIN rental r ON r.inventory_id = i.inventory_id "
            "GROUP BY f.title ORDER BY rentals DESC LIMIT 1",
            "response": {
                "response_type": "data_table",
                "data": {"columns": ["title", "rentals"], "rows": [["ACADEMY DINOSAUR", 32]]},
            },
        },
    )
    content = _assistant_content(msg)
    assert "ACADEMY DINOSAUR" in content
    assert "32" in content


def test_assistant_content_includes_kpi_value() -> None:
    msg = ChatMessage(
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        role="assistant",
        content="",
        metadata_json={
            "response": {"response_type": "kpi_card", "data": {"label": "count", "value": 1000}},
        },
    )
    content = _assistant_content(msg)
    assert "1000" in content
