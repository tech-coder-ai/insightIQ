from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.models import AuditEvent
from core.request_context import RequestContext, require_role
from core.types import Role

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str | None
    user_id: uuid.UUID | None
    correlation_id: str | None
    metadata_json: dict
    created_at: str


@router.get("/audit", response_model=list[AuditEventResponse])
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    ctx: RequestContext = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEventResponse]:
    res = await db.execute(
        select(AuditEvent)
        .where(AuditEvent.tenant_id == ctx.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    return [
        AuditEventResponse(
            id=e.id,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            user_id=e.user_id,
            correlation_id=e.correlation_id,
            metadata_json=e.metadata_json,
            created_at=e.created_at.isoformat(),
        )
        for e in res.scalars().all()
    ]
