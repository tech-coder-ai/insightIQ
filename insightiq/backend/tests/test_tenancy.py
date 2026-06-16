from __future__ import annotations

import uuid

import pytest

from core.models import Dashboard
from core.request_context import RequestContext
from core.tenancy import assert_tenant_match, user_can_access_dashboard, user_can_edit_dashboard
from core.types import Role


def _ctx(*, user_id: uuid.UUID | None = None, tenant_id: uuid.UUID | None = None, role: Role = Role.viewer) -> RequestContext:
    return RequestContext(
        user_id=user_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        role=role,
    )


def test_assert_tenant_match_ok() -> None:
    tenant = uuid.uuid4()
    row = Dashboard(tenant_id=tenant, owner_user_id=uuid.uuid4(), name="x")
    assert_tenant_match(row, tenant)


def test_assert_tenant_match_raises() -> None:
    row = Dashboard(tenant_id=uuid.uuid4(), owner_user_id=uuid.uuid4(), name="x")
    with pytest.raises(PermissionError):
        assert_tenant_match(row, uuid.uuid4())


def test_dashboard_owner_access() -> None:
    tenant = uuid.uuid4()
    owner = uuid.uuid4()
    dash = Dashboard(tenant_id=tenant, owner_user_id=owner, name="sales")
    ctx = _ctx(user_id=owner, tenant_id=tenant)
    assert user_can_access_dashboard(dash, ctx)
    assert user_can_edit_dashboard(dash, ctx)


def test_dashboard_team_viewer_access() -> None:
    tenant = uuid.uuid4()
    viewer = uuid.uuid4()
    dash = Dashboard(
        tenant_id=tenant,
        owner_user_id=uuid.uuid4(),
        name="sales",
        team_access_json=[{"user_id": str(viewer), "role": "viewer"}],
    )
    ctx = _ctx(user_id=viewer, tenant_id=tenant)
    assert user_can_access_dashboard(dash, ctx)
    assert not user_can_edit_dashboard(dash, ctx)


def test_dashboard_cross_tenant_denied() -> None:
    dash = Dashboard(tenant_id=uuid.uuid4(), owner_user_id=uuid.uuid4(), name="sales")
    ctx = _ctx(tenant_id=uuid.uuid4())
    assert not user_can_access_dashboard(dash, ctx)
