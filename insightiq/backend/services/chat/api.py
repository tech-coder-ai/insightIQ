from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ChatMessage
from core.request_context import RequestContext, require_auth
from services.auth.api import get_db


router = APIRouter(prefix="/chat", tags=["chat"])


class CreateMessageRequest(BaseModel):
    conversation_id: uuid.UUID
    role: str = Field(pattern=r"^(user|assistant|system)$")
    content: str = Field(min_length=1)
    metadata_json: dict = Field(default_factory=dict)


class CreateMessageResponse(BaseModel):
    id: uuid.UUID


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

