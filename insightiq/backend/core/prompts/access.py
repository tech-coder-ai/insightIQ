from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import PromptTemplate, PromptVersion
from core.request_context import RequestContext


async def load_accessible_template(
    db: AsyncSession,
    ctx: RequestContext,
    template_id: uuid.UUID,
) -> tuple[PromptTemplate, PromptVersion]:
    res = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == ctx.tenant_id,
            or_(PromptTemplate.owner_user_id == ctx.user_id, PromptTemplate.is_shared.is_(True)),
        )
    )
    tmpl = res.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="prompt template not found")

    ver_res = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.template_id == tmpl.id)
        .order_by(PromptVersion.version_number.desc())
        .limit(1)
    )
    version = ver_res.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="prompt template has no versions")
    return tmpl, version
