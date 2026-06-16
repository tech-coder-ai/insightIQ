from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.jobs.report_scheduler import run_scheduled_report
from core.models import Dashboard, ScheduledReport
from core.request_context import RequestContext, require_auth, require_role
from core.tenancy import user_can_edit_dashboard
from core.types import Role

router = APIRouter(prefix="/reports", tags=["reports"])


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    dashboard_id: uuid.UUID
    recipient_email: str
    interval_seconds: int
    export_format: str
    enabled: bool
    next_run_at: str | None


class CreateScheduleRequest(BaseModel):
    dashboard_id: uuid.UUID
    recipient_email: EmailStr
    interval_seconds: int = Field(default=3600, ge=300, le=604800)
    export_format: str = Field(default="pdf", pattern=r"^(pdf|pptx)$")


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(
    req: CreateScheduleRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> ScheduleResponse:
    dash = await _get_editable_dashboard(db, ctx, req.dashboard_id)
    now = datetime.now(UTC)
    report = ScheduledReport(
        tenant_id=ctx.tenant_id,
        dashboard_id=dash.id,
        owner_user_id=ctx.user_id,
        recipient_email=str(req.recipient_email),
        interval_seconds=req.interval_seconds,
        export_format=req.export_format,
        next_run_at=now + timedelta(seconds=req.interval_seconds),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _schedule_response(report)


@router.get("/schedules", response_model=list[ScheduleResponse])
async def list_schedules(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[ScheduleResponse]:
    res = await db.execute(
        select(ScheduledReport).where(
            ScheduledReport.tenant_id == ctx.tenant_id,
            ScheduledReport.owner_user_id == ctx.user_id,
        )
    )
    return [_schedule_response(r) for r in res.scalars().all()]


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    report = await _get_schedule(db, ctx, schedule_id)
    await db.delete(report)
    await db.commit()
    return {"status": "deleted"}


@router.post("/schedules/{schedule_id}/run-now")
async def run_schedule_now(
    schedule_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    await _get_schedule(db, ctx, schedule_id)
    await run_scheduled_report(schedule_id)
    return {"status": "sent"}


async def _get_editable_dashboard(db: AsyncSession, ctx: RequestContext, dashboard_id: uuid.UUID) -> Dashboard:
    res = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.tenant_id == ctx.tenant_id)
    )
    dash = res.scalar_one_or_none()
    if dash is None:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not user_can_edit_dashboard(dash, ctx):
        raise HTTPException(status_code=403, detail="dashboard edit forbidden")
    return dash


async def _get_schedule(db: AsyncSession, ctx: RequestContext, schedule_id: uuid.UUID) -> ScheduledReport:
    res = await db.execute(
        select(ScheduledReport).where(
            ScheduledReport.id == schedule_id,
            ScheduledReport.tenant_id == ctx.tenant_id,
            ScheduledReport.owner_user_id == ctx.user_id,
        )
    )
    report = res.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return report


def _schedule_response(r: ScheduledReport) -> ScheduleResponse:
    return ScheduleResponse(
        id=r.id,
        dashboard_id=r.dashboard_id,
        recipient_email=r.recipient_email,
        interval_seconds=r.interval_seconds,
        export_format=r.export_format,
        enabled=r.enabled,
        next_run_at=r.next_run_at.isoformat() if r.next_run_at else None,
    )
