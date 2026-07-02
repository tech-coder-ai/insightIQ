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


class UpdateCardRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    layout_json: dict[str, Any] | None = None
    refresh_mode: str | None = None
    auto_refresh_seconds: int | None = Field(default=None, ge=30, le=86400)


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
    _validate_refresh_mode(req.refresh_mode)

    layout_json = dict(req.layout_json)
    new_rows = max(int(layout_json.get("rows", 3)), 2)
    new_cols = int(layout_json.get("cols", 4))
    layout_json["x"] = int(layout_json.get("x", 0))
    layout_json["y"] = 0
    layout_json["cols"] = new_cols
    layout_json["rows"] = new_rows

    cards_res = await db.execute(select(DashboardCard).where(DashboardCard.dashboard_id == dashboard_id))
    for existing in cards_res.scalars().all():
        layout = dict(existing.layout_json or {})
        layout["y"] = int(layout.get("y", 0)) + new_rows
        existing.layout_json = layout

    card = DashboardCard(
        dashboard_id=dashboard_id,
        tenant_id=ctx.tenant_id,
        title=req.title,
        card_type=req.card_type,
        layout_json=layout_json,
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
async def update_card(
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    req: UpdateCardRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    if (
        req.title is None
        and req.layout_json is None
        and req.refresh_mode is None
        and "auto_refresh_seconds" not in req.model_fields_set
    ):
        raise HTTPException(status_code=400, detail="no updates provided")
    card = await _get_card(db, ctx, dashboard_id, card_id, require_edit=True)
    if req.title is not None:
        card.title = req.title
    if req.layout_json is not None:
        card.layout_json = req.layout_json
    if req.refresh_mode is not None:
        _validate_refresh_mode(req.refresh_mode)
        card.refresh_mode = req.refresh_mode
        if req.refresh_mode == "snapshot":
            card.auto_refresh_seconds = None
    if "auto_refresh_seconds" in req.model_fields_set:
        if card.refresh_mode != "live" and req.auto_refresh_seconds is not None:
            raise HTTPException(status_code=400, detail="auto_refresh_seconds requires live refresh mode")
        card.auto_refresh_seconds = req.auto_refresh_seconds
    await db.commit()
    await db.refresh(card)
    return _card_response(card)


@router.delete("/{dashboard_id}/cards/{card_id}", status_code=204)
async def delete_card(
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    request: Request,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> None:
    card = await _get_card(db, ctx, dashboard_id, card_id, require_edit=True)
    card_title = card.title
    await db.delete(card)
    await record_audit(
        db,
        action="delete_card",
        resource_type="dashboard_card",
        resource_id=str(card_id),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        metadata={"dashboard_id": str(dashboard_id), "title": card_title},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()


@router.post("/{dashboard_id}/cards/{card_id}/refresh", response_model=CardResponse)
async def refresh_card(
    dashboard_id: uuid.UUID,
    card_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> CardResponse:
    card = await _get_card(db, ctx, dashboard_id, card_id, require_edit=False)
    if card.refresh_mode == "snapshot":
        return _card_response(card)

    dash = await _get_dashboard(db, ctx, dashboard_id)
    refresher = CardRefresherFactory.create(card.source_type)
    result = await refresher.refresh(
        source_config=card.source_config_json,
        tenant_id=str(ctx.tenant_id),
        filters=dash.global_filters_json or None,
    )
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


def _validate_refresh_mode(refresh_mode: str) -> None:
    if refresh_mode not in {"snapshot", "live"}:
        raise HTTPException(status_code=400, detail="refresh_mode must be snapshot or live")


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
