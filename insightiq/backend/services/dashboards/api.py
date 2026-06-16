from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit.service import record_audit
from core.dashboard.factory import CardRefresherFactory
from core.deps import get_db
from core.models import Dashboard, DashboardCard, DashboardShare
from core.request_context import RequestContext, require_auth, require_role
from core.tenancy import user_can_access_dashboard, user_can_edit_dashboard
from core.types import Role

router = APIRouter(prefix="/dashboards", tags=["dashboards"])
public_router = APIRouter(prefix="/public/dashboards", tags=["public-dashboards"])


class DashboardResponse(BaseModel):
    id: uuid.UUID
    name: str
    global_filters_json: dict
    team_access_json: list


class CardResponse(BaseModel):
    id: uuid.UUID
    title: str
    card_type: str
    layout_json: dict
    refresh_mode: str
    source_type: str
    snapshot_response_json: dict
    auto_refresh_seconds: int | None


class DashboardDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    global_filters_json: dict
    cards: list[CardResponse]


class CreateDashboardRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PinCardRequest(BaseModel):
    title: str
    card_type: str
    response: dict[str, Any]
    source_type: str  # sql | rag
    source_config: dict[str, Any]
    refresh_mode: str = "snapshot"
    layout_json: dict[str, Any] = Field(default_factory=lambda: {"x": 0, "y": 0, "cols": 4, "rows": 3})
    auto_refresh_seconds: int | None = None


class UpdateCardLayoutRequest(BaseModel):
    layout_json: dict[str, Any]


class UpdateFiltersRequest(BaseModel):
    global_filters_json: dict[str, Any]


class UpdateTeamAccessRequest(BaseModel):
    team_access_json: list[dict[str, str]]


class ShareResponse(BaseModel):
    token: str
    url_path: str


@router.post("", response_model=DashboardResponse)
async def create_dashboard(
    req: CreateDashboardRequest,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    dash = Dashboard(tenant_id=ctx.tenant_id, owner_user_id=ctx.user_id, name=req.name)
    db.add(dash)
    await db.flush()
    await record_audit(
        db,
        action="create",
        resource_type="dashboard",
        resource_id=str(dash.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(dash)
    return DashboardResponse(
        id=dash.id, name=dash.name, global_filters_json=dash.global_filters_json, team_access_json=list(dash.team_access_json)
    )


@router.get("", response_model=list[DashboardResponse])
async def list_dashboards(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DashboardResponse]:
    res = await db.execute(select(Dashboard).where(Dashboard.tenant_id == ctx.tenant_id))
    dashboards = [d for d in res.scalars().all() if user_can_access_dashboard(d, ctx)]
    return [
        DashboardResponse(
            id=d.id, name=d.name, global_filters_json=d.global_filters_json, team_access_json=list(d.team_access_json)
        )
        for d in dashboards
    ]


@router.get("/{dashboard_id}", response_model=DashboardDetailResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> DashboardDetailResponse:
    dash = await _get_dashboard(db, ctx, dashboard_id)
    cards_res = await db.execute(select(DashboardCard).where(DashboardCard.dashboard_id == dash.id))
    cards = [_card_response(c) for c in cards_res.scalars().all()]
    return DashboardDetailResponse(
        id=dash.id, name=dash.name, global_filters_json=dash.global_filters_json, cards=cards
    )


@router.patch("/{dashboard_id}/filters", response_model=DashboardResponse)
async def update_filters(
    dashboard_id: uuid.UUID,
    req: UpdateFiltersRequest,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    dash = await _get_dashboard(db, ctx, dashboard_id, require_edit=True)
    dash.global_filters_json = req.global_filters_json
    await record_audit(
        db,
        action="update_filters",
        resource_type="dashboard",
        resource_id=str(dash.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return DashboardResponse(
        id=dash.id, name=dash.name, global_filters_json=dash.global_filters_json, team_access_json=list(dash.team_access_json)
    )


@router.patch("/{dashboard_id}/team-access", response_model=DashboardResponse)
async def update_team_access(
    dashboard_id: uuid.UUID,
    req: UpdateTeamAccessRequest,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    dash = await _get_dashboard(db, ctx, dashboard_id, require_edit=True)
    dash.team_access_json = req.team_access_json
    await record_audit(
        db,
        action="update_team_access",
        resource_type="dashboard",
        resource_id=str(dash.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"team_size": len(req.team_access_json)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return DashboardResponse(
        id=dash.id, name=dash.name, global_filters_json=dash.global_filters_json, team_access_json=list(dash.team_access_json)
    )


@router.post("/{dashboard_id}/cards", response_model=CardResponse)
async def pin_card(
    dashboard_id: uuid.UUID,
    req: PinCardRequest,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    await _get_dashboard(db, ctx, dashboard_id, require_edit=True)
    card = DashboardCard(
        dashboard_id=dashboard_id,
        tenant_id=ctx.tenant_id,
        title=req.title,
        card_type=req.card_type,
        layout_json=req.layout_json,
        refresh_mode=req.refresh_mode,
        source_type=req.source_type,
        source_config_json=req.source_config,
        snapshot_response_json=req.response,
        auto_refresh_seconds=req.auto_refresh_seconds,
    )
    db.add(card)
    await db.flush()
    await record_audit(
        db,
        action="pin_card",
        resource_type="dashboard_card",
        resource_id=str(card.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"dashboard_id": str(dashboard_id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(card)
    return _card_response(card)


@router.patch("/{dashboard_id}/cards/{card_id}", response_model=CardResponse)
async def update_card_layout(
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    req: UpdateCardLayoutRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    card = await _get_card(db, ctx, dashboard_id, card_id, require_edit=True)
    card.layout_json = req.layout_json
    await db.commit()
    await db.refresh(card)
    return _card_response(card)


@router.post("/{dashboard_id}/cards/{card_id}/refresh", response_model=CardResponse)
async def refresh_card(
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    card = await _get_card(db, ctx, dashboard_id, card_id, require_edit=False)
        return _card_response(card)

    refresher = CardRefresherFactory.create(card.source_type)
    result = await refresher.refresh(source_config=card.source_config_json, tenant_id=str(ctx.tenant_id))
    card.snapshot_response_json = result.response
    await db.commit()
    await db.refresh(card)
    return _card_response(card)


@router.post("/{dashboard_id}/share", response_model=ShareResponse)
async def share_dashboard(
    dashboard_id: uuid.UUID,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> ShareResponse:
    dash = await _get_dashboard(db, ctx, dashboard_id, require_edit=True)
    token = secrets.token_urlsafe(24)
    share = DashboardShare(
        dashboard_id=dash.id,
        tenant_id=ctx.tenant_id,
        token=token,
        read_only=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(share)
    await db.flush()
    await record_audit(
        db,
        action="share",
        resource_type="dashboard",
        resource_id=str(dash.id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return ShareResponse(token=token, url_path=f"/d/{token}")


@public_router.get("/{token}", response_model=DashboardDetailResponse)
async def public_dashboard(token: str, db: AsyncSession = Depends(get_db)) -> DashboardDetailResponse:
    res = await db.execute(select(DashboardShare).where(DashboardShare.token == token))
    share = res.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=404, detail="share not found")
    if share.expires_at and share.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=410, detail="share expired")

    dash = await db.get(Dashboard, share.dashboard_id)
    if dash is None:
        raise HTTPException(status_code=404, detail="dashboard not found")

    cards_res = await db.execute(select(DashboardCard).where(DashboardCard.dashboard_id == dash.id))
    cards = [_card_response(c) for c in cards_res.scalars().all()]
    return DashboardDetailResponse(
        id=dash.id, name=dash.name, global_filters_json=dash.global_filters_json, cards=cards
    )


async def _get_dashboard(
    db: AsyncSession,
    ctx: RequestContext,
    dashboard_id: uuid.UUID,
    *,
    require_edit: bool = False,
) -> Dashboard:
    res = await db.execute(
        select(Dashboard).where(Dashboard.id == dashboard_id, Dashboard.tenant_id == ctx.tenant_id)
    )
    dash = res.scalar_one_or_none()
    if dash is None:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if require_edit and not user_can_edit_dashboard(dash, ctx):
        raise HTTPException(status_code=403, detail="dashboard edit forbidden")
    if not require_edit and not user_can_access_dashboard(dash, ctx):
        raise HTTPException(status_code=403, detail="dashboard access forbidden")
    return dash


async def _get_card(
    db: AsyncSession,
    ctx: RequestContext,
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    *,
    require_edit: bool = False,
) -> DashboardCard:
    dash = await _get_dashboard(db, ctx, dashboard_id, require_edit=require_edit)
    res = await db.execute(
        select(DashboardCard).where(
            DashboardCard.id == card_id,
            DashboardCard.dashboard_id == dash.id,
            DashboardCard.tenant_id == ctx.tenant_id,
        )
    )
    card = res.scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    return card


def _card_response(c: DashboardCard) -> CardResponse:
    return CardResponse(
        id=c.id,
        title=c.title,
        card_type=c.card_type,
        layout_json=c.layout_json,
        refresh_mode=c.refresh_mode,
        source_type=c.source_type,
        snapshot_response_json=c.snapshot_response_json,
        auto_refresh_seconds=c.auto_refresh_seconds,
    )
