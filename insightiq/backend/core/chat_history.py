from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.base import LLMMessage
from core.models import ChatMessage
from core.rag.state import Message
from core.request_context import RequestContext

MAX_CONVERSATION_HISTORY_MESSAGES = 20


def _assistant_content(msg: ChatMessage) -> str:
    meta: dict[str, Any] = msg.metadata_json or {}
    parts: list[str] = []
    sql = meta.get("sql")
    if sql:
        parts.append(f"SQL executed:\n{sql}")
    response = meta.get("response")
    if isinstance(response, dict):
        data = response.get("data") or {}
        output = data.get("output")
        if output:
            parts.append(str(output))
    if parts:
        return "\n\n".join(parts)
    return msg.content or ""


def chat_message_to_llm(msg: ChatMessage) -> LLMMessage:
    role = msg.role if msg.role in {"user", "assistant", "system"} else "user"
    content = _assistant_content(msg) if role == "assistant" else (msg.content or "")
    return LLMMessage(role=role, content=content)


def chat_message_to_rag(msg: ChatMessage) -> Message:
    llm = chat_message_to_llm(msg)
    return Message(role=llm.role, content=llm.content)


def _has_content(msg: ChatMessage) -> bool:
    if msg.role == "assistant":
        return bool(_assistant_content(msg).strip())
    return bool((msg.content or "").strip())


async def load_conversation_messages(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    *,
    limit: int = MAX_CONVERSATION_HISTORY_MESSAGES,
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.tenant_id == ctx.tenant_id,
        )
        .order_by(ChatMessage.created_at.asc())
    )
    rows = [m for m in result.scalars().all() if _has_content(m)]
    if len(rows) > limit:
        rows = rows[-limit:]
    return rows


async def load_llm_history(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    *,
    limit: int = MAX_CONVERSATION_HISTORY_MESSAGES,
) -> list[LLMMessage]:
    rows = await load_conversation_messages(db, ctx, conversation_id, limit=limit)
    return [chat_message_to_llm(m) for m in rows]


async def load_rag_history(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    *,
    limit: int = MAX_CONVERSATION_HISTORY_MESSAGES,
) -> list[Message]:
    rows = await load_conversation_messages(db, ctx, conversation_id, limit=limit)
    return [chat_message_to_rag(m) for m in rows]
