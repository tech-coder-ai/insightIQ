from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.models import ChatMessage, Conversation
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


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    folder: str | None
    tags: list[str]
    starred: bool
    datasource_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class UpdateConversationRequest(BaseModel):
    title: str | None = None
    folder: str | None = None
    tags: list[str] | None = None
    starred: bool | None = None


class ForkConversationResponse(BaseModel):
    id: uuid.UUID


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    q: str | None = None,
    starred: bool | None = None,
    datasource_id: uuid.UUID | None = None,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    stmt = select(Conversation).where(
        Conversation.tenant_id == ctx.tenant_id,
        Conversation.user_id == ctx.user_id,
    )
    if datasource_id is not None:
        stmt = stmt.where(Conversation.datasource_id == datasource_id)
    if starred is not None:
        stmt = stmt.where(Conversation.starred == starred)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(Conversation.title.ilike(pattern), Conversation.folder.ilike(pattern))
        )
    stmt = stmt.order_by(Conversation.updated_at.desc())
    res = await db.execute(stmt)
    return [_conv_response(c) for c in res.scalars().all()]


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    req: UpdateConversationRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    conv = await _get_conversation(db, ctx, conversation_id)
    if req.title is not None:
        conv.title = req.title
    if req.folder is not None:
        conv.folder = req.folder
    if req.tags is not None:
        conv.tags = req.tags
    if req.starred is not None:
        conv.starred = req.starred
    await db.commit()
    await db.refresh(conv)
    return _conv_response(conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    conv = await _get_conversation(db, ctx, conversation_id)
    await db.execute(
        delete(ChatMessage).where(
            ChatMessage.conversation_id == conv.id,
            ChatMessage.tenant_id == ctx.tenant_id,
        )
    )
    await db.delete(conv)
    await db.commit()


@router.post("/conversations/{conversation_id}/fork", response_model=ForkConversationResponse)
async def fork_conversation(
    conversation_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> ForkConversationResponse:
    conv = await _get_conversation(db, ctx, conversation_id)
    new_id = uuid.uuid4()
    db.add(
        Conversation(
            id=new_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            title=f"{conv.title} (fork)",
            folder=conv.folder,
            tags=list(conv.tags),
            starred=False,
            datasource_id=conv.datasource_id,
        )
    )
    msgs = await db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    )
    for m in msgs.scalars().all():
        db.add(
            ChatMessage(
                tenant_id=m.tenant_id,
                user_id=m.user_id,
                conversation_id=new_id,
                role=m.role,
                content=m.content,
                metadata_json=dict(m.metadata_json),
            )
        )
    await db.commit()
    return ForkConversationResponse(id=new_id)


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


async def _get_conversation(
    db: AsyncSession, ctx: RequestContext, conversation_id: uuid.UUID
) -> Conversation:
    res = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == ctx.tenant_id,
            Conversation.user_id == ctx.user_id,
        )
    )
    conv = res.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


def _conv_response(c: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=c.id,
        title=c.title,
        folder=c.folder,
        tags=list(c.tags),
        starred=c.starred,
        datasource_id=c.datasource_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )
