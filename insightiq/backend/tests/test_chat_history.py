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
