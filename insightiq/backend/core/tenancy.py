from __future__ import annotations

import uuid
from typing import Protocol

from core.models import Dashboard
from core.request_context import RequestContext
from core.types import Role


class TenantScoped(Protocol):
    tenant_id: uuid.UUID


def assert_tenant_match(row: TenantScoped, tenant_id: uuid.UUID) -> None:
    if row.tenant_id != tenant_id:
        raise PermissionError("tenant mismatch")


def user_can_access_dashboard(dashboard: Dashboard, ctx: RequestContext) -> bool:
    if dashboard.tenant_id != ctx.tenant_id:
        return False
    if ctx.role in (Role.admin, Role.super_admin):
        return True
    if dashboard.owner_user_id == ctx.user_id:
        return True
    for entry in dashboard.team_access_json or []:
        if isinstance(entry, dict) and str(entry.get("user_id")) == str(ctx.user_id):
            return True
        if isinstance(entry, str) and entry == str(ctx.user_id):
            return True
    return False


def user_can_edit_dashboard(dashboard: Dashboard, ctx: RequestContext) -> bool:
    if dashboard.tenant_id != ctx.tenant_id:
        return False
    if ctx.role in (Role.admin, Role.super_admin):
        return True
    if dashboard.owner_user_id == ctx.user_id:
        return True
    for entry in dashboard.team_access_json or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("user_id")) != str(ctx.user_id):
            continue
        if entry.get("role") in ("editor", "admin"):
            return True
    return False
