from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.export.base import ExportPayload
from core.export.factory import ExporterFactory
from core.jobs.report_scheduler import build_dashboard_export_payload
from core.models import ChatMessage, Conversation, Dashboard
from core.request_context import RequestContext, require_auth
from core.tenancy import user_can_access_dashboard

router = APIRouter(prefix="/export", tags=["export"])


class ExportFormatsResponse(BaseModel):
    formats: list[str]


@router.get("/formats", response_model=ExportFormatsResponse)
async def list_formats() -> ExportFormatsResponse:
    return ExportFormatsResponse(formats=ExporterFactory.keys())


@router.get("/conversations/{conversation_id}")
async def export_conversation(
    conversation_id: uuid.UUID,
    format: str = Query(default="markdown", pattern=r"^(markdown|pdf|pptx)$"),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    conv = await _get_conversation(db, ctx, conversation_id)
    msgs_res = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.tenant_id == ctx.tenant_id,
        )
        .order_by(ChatMessage.created_at.asc())
    )
    messages = [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in msgs_res.scalars().all()
    ]
    payload = ExportPayload(
        title=conv.title,
        content_type="conversation",
        data={"messages": messages},
    )
    exporter = ExporterFactory.create(format)
    result = await exporter.export(payload=payload)
    return Response(content=result.data, media_type=result.media_type, headers={"Content-Disposition": f'attachment; filename="{result.filename}"'})


@router.get("/dashboards/{dashboard_id}")
async def export_dashboard(
    dashboard_id: uuid.UUID,
    format: str = Query(default="pdf", pattern=r"^(pdf|pptx|markdown)$"),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Response:
    dash = await _get_dashboard(db, ctx, dashboard_id)
    payload = await build_dashboard_export_payload(db, dashboard=dash, tenant_id=ctx.tenant_id)
    exporter = ExporterFactory.create(format)
    result = await exporter.export(payload=payload)
    await db.commit()
    return Response(content=result.data, media_type=result.media_type, headers={"Content-Disposition": f'attachment; filename="{result.filename}"'})


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


async def _get_dashboard(db: AsyncSession, ctx: RequestContext, dashboard_id: uuid.UUID) -> Dashboard:
    res = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.tenant_id == ctx.tenant_id)
    )
    dash = res.scalar_one_or_none()
    if dash is None:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not user_can_access_dashboard(dash, ctx):
        raise HTTPException(status_code=403, detail="dashboard access forbidden")
    return dash
