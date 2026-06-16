from __future__ import annotations

import uuid

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.models import ChatMessage
from core.request_context import RequestContext, require_auth


router = APIRouter(prefix="/chat", tags=["chat"])


class CreateMessageRequest(BaseModel):
    conversation_id: uuid.UUID
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str = Field(min_length=1)
    metadata_json: dict = Field(default_factory=dict)


class CreateMessageResponse(BaseModel):
    id: uuid.UUID


class MessageResponse(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    metadata_json: dict
    created_at: dt.datetime


@router.get("/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    res = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.tenant_id == ctx.tenant_id,
            ChatMessage.conversation_id == conversation_id,
        )
        .order_by(ChatMessage.created_at.asc())
    )
    return [
        MessageResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            metadata_json=m.metadata_json,
            created_at=m.created_at,
        )
        for m in res.scalars().all()
    ]


@router.post("/messages", response_model=CreateMessageResponse)
async def create_message(
    req: CreateMessageRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> CreateMessageResponse:
    msg = ChatMessage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation_id=req.conversation_id,
        role=req.role,
        content=req.content,
        metadata_json=req.metadata_json,
    )
    db.add(msg)
    await db.commit()
    return CreateMessageResponse(id=msg.id)

