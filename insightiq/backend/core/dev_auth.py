from __future__ import annotations

import uuid

from sqlalchemy import select

from config.settings import get_settings_resolver
from core.deps import get_app_sessionmaker
from core.models import Tenant, User
from core.security import hash_password
from core.types import Role

DEV_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


async def ensure_dev_identity() -> None:
    settings = get_settings_resolver().resolve()
    if not settings.auth.disabled:
        return

    sessionmaker = get_app_sessionmaker()
    async with sessionmaker() as db:
        tenant = await db.get(Tenant, DEV_TENANT_ID)
        if tenant is None:
            db.add(Tenant(id=DEV_TENANT_ID, name="dev"))
        res = await db.execute(select(User).where(User.id == DEV_USER_ID))
        user = res.scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    id=DEV_USER_ID,
                    tenant_id=DEV_TENANT_ID,
                    email="dev@insightiq.local",
                    password_hash=hash_password("dev-only"),
                    role=Role.admin,
                )
            )
        await db.commit()
