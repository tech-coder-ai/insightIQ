from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.models import DashboardCard, PromptRun, PromptTemplate, PromptVersion
from core.prompts.bindings import merge_template_variables, resolve_binding_context
from core.prompts.judge import judge_output
from core.prompts.renderer import render_template
from core.request_context import RequestContext, require_auth, require_role
from core.response.types import ResponsePayload, ResponseType
from core.types import Role

router = APIRouter(prefix="/prompt-studio", tags=["prompt-studio"])


class TemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    bindings_json: dict
    is_shared: bool
    is_mine: bool = False
    owner_user_id: uuid.UUID | None = None
    latest_version: int | None = None


class CreateTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    bindings_json: dict[str, Any] = Field(default_factory=dict)
    template_body: str = Field(min_length=1)
    system_prompt: str = ""
    variables_schema_json: dict[str, Any] = Field(default_factory=dict)


class UpdateTemplateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    bindings_json: dict[str, Any] | None = None


class TemplateDetailResponse(TemplateResponse):
    latest_version_id: uuid.UUID | None = None
    template_body: str = ""
    system_prompt: str = ""
    variables_schema_json: dict[str, Any] = Field(default_factory=dict)


class VersionCreateRequest(BaseModel):
    template_body: str = Field(min_length=1)
    system_prompt: str = ""
    variables_schema_json: dict[str, Any] = Field(default_factory=dict)


class VersionResponse(BaseModel):
    id: uuid.UUID
    version_number: int
    template_body: str
    system_prompt: str
    variables_schema_json: dict
    created_at: str


class RunRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    version_id: uuid.UUID | None = None
    llm_provider: str = "heuristic"


class RunResponse(BaseModel):
    run_id: uuid.UUID
    rendered_prompt: str
    output: str
    eval_scores: dict
    response: dict
    context_preview: str = ""


class PinRunRequest(BaseModel):
    dashboard_id: uuid.UUID
    title: str | None = None
    refresh_mode: str = "snapshot"


@router.post("/templates", response_model=TemplateResponse)
async def create_template(
    req: CreateTemplateRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    tmpl = PromptTemplate(
        tenant_id=ctx.tenant_id,
        owner_user_id=ctx.user_id,
        name=req.name,
        description=req.description,
        bindings_json=req.bindings_json,
    )
    db.add(tmpl)
    await db.flush()
    version = PromptVersion(
        template_id=tmpl.id,
        tenant_id=ctx.tenant_id,
        version_number=1,
        template_body=req.template_body,
        system_prompt=req.system_prompt,
        variables_schema_json=req.variables_schema_json,
        created_by=ctx.user_id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(tmpl)
    return TemplateResponse(
        id=tmpl.id,
        name=tmpl.name,
        description=tmpl.description,
        bindings_json=tmpl.bindings_json,
        is_shared=tmpl.is_shared,
        is_mine=True,
        owner_user_id=tmpl.owner_user_id,
        latest_version=1,
    )


@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    scope: str = Query(default="all", pattern="^(all|mine|shared)$"),
    binding: str | None = Query(default=None, pattern="^(none|sql|rag|file)$"),
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateResponse]:
    conditions = [PromptTemplate.tenant_id == ctx.tenant_id]
    if scope == "mine":
        conditions.append(PromptTemplate.owner_user_id == ctx.user_id)
    elif scope == "shared":
        conditions.append(PromptTemplate.is_shared.is_(True))
        conditions.append(PromptTemplate.owner_user_id != ctx.user_id)
    else:
        conditions.append(
            or_(PromptTemplate.owner_user_id == ctx.user_id, PromptTemplate.is_shared.is_(True))
        )

    res = await db.execute(select(PromptTemplate).where(*conditions))
    templates = res.scalars().all()
    out: list[TemplateResponse] = []
    for tmpl in templates:
        binding_type = (tmpl.bindings_json or {}).get("type", "none")
        if binding and binding_type != binding:
            continue
        ver_res = await db.execute(
            select(func.max(PromptVersion.version_number)).where(PromptVersion.template_id == tmpl.id)
        )
        latest = ver_res.scalar_one()
        out.append(
            TemplateResponse(
                id=tmpl.id,
                name=tmpl.name,
                description=tmpl.description,
                bindings_json=tmpl.bindings_json,
                is_shared=tmpl.is_shared,
                is_mine=tmpl.owner_user_id == ctx.user_id,
                owner_user_id=tmpl.owner_user_id,
                latest_version=latest,
            )
        )
    out.sort(key=lambda t: (not t.is_mine, t.name.lower()))
    return out


@router.get("/templates/{template_id}", response_model=TemplateDetailResponse)
async def get_template(
    template_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> TemplateDetailResponse:
    tmpl = await _get_template(db, ctx, template_id)
    version = await _get_version(db, tmpl.id, None)
    ver_res = await db.execute(
        select(func.max(PromptVersion.version_number)).where(PromptVersion.template_id == tmpl.id)
    )
    return TemplateDetailResponse(
        id=tmpl.id,
        name=tmpl.name,
        description=tmpl.description,
        bindings_json=tmpl.bindings_json,
        is_shared=tmpl.is_shared,
        is_mine=tmpl.owner_user_id == ctx.user_id,
        owner_user_id=tmpl.owner_user_id,
        latest_version=ver_res.scalar_one(),
        latest_version_id=version.id,
        template_body=version.template_body,
        system_prompt=version.system_prompt,
        variables_schema_json=version.variables_schema_json,
    )


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    req: UpdateTemplateRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    tmpl = await _get_template(db, ctx, template_id, owner_only=True)
    if req.name is not None:
        tmpl.name = req.name
    if req.description is not None:
        tmpl.description = req.description
    if req.bindings_json is not None:
        tmpl.bindings_json = req.bindings_json
    await db.commit()
    ver_res = await db.execute(
        select(func.max(PromptVersion.version_number)).where(PromptVersion.template_id == tmpl.id)
    )
    return TemplateResponse(
        id=tmpl.id,
        name=tmpl.name,
        description=tmpl.description,
        bindings_json=tmpl.bindings_json,
        is_shared=tmpl.is_shared,
        is_mine=True,
        owner_user_id=tmpl.owner_user_id,
        latest_version=ver_res.scalar_one(),
    )


@router.post("/templates/{template_id}/versions", response_model=VersionResponse)
async def create_version(
    template_id: uuid.UUID,
    req: VersionCreateRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> VersionResponse:
    tmpl = await _get_template(db, ctx, template_id, owner_only=True)
    ver_res = await db.execute(
        select(func.max(PromptVersion.version_number)).where(PromptVersion.template_id == tmpl.id)
    )
    next_ver = (ver_res.scalar_one() or 0) + 1
    version = PromptVersion(
        template_id=tmpl.id,
        tenant_id=ctx.tenant_id,
        version_number=next_ver,
        template_body=req.template_body,
        system_prompt=req.system_prompt,
        variables_schema_json=req.variables_schema_json,
        created_by=ctx.user_id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return _version_response(version)


@router.get("/templates/{template_id}/versions", response_model=list[VersionResponse])
async def list_versions(
    template_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[VersionResponse]:
    await _get_template(db, ctx, template_id)
    res = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.template_id == template_id)
        .order_by(PromptVersion.version_number.desc())
    )
    return [_version_response(v) for v in res.scalars().all()]


@router.post("/templates/{template_id}/run", response_model=RunResponse)
async def run_template(
    template_id: uuid.UUID,
    req: RunRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> RunResponse:
    tmpl = await _get_template(db, ctx, template_id)
    version = await _get_version(db, tmpl.id, req.version_id)
    try:
        context_text, context_vars = await resolve_binding_context(
            db,
            tenant_id=ctx.tenant_id,
            bindings=tmpl.bindings_json,
            variables=req.variables,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    merged_variables = merge_template_variables(
        context_text=context_text,
        context_vars=context_vars,
        variables=req.variables,
    )
    rendered = render_template(version.template_body, merged_variables)
    user_prompt = rendered
    if context_text:
        user_prompt = f"Context:\n{context_text}\n\nTask:\n{rendered}"

    try:
        llm = LLMProviderFactory.create("openai")
    except Exception:  # noqa: BLE001
        llm = LLMProviderFactory.create(req.llm_provider or "heuristic")

    output = await llm.complete(
        system=version.system_prompt or "You are a helpful analyst.",
        messages=[LLMMessage(role="user", content=user_prompt)],
    )
    keywords = list(req.variables.values()) if req.variables else []
    scores = await judge_output(
        prompt=rendered,
        output=output,
        expected_keywords=[str(k) for k in keywords],
    )
    payload = ResponsePayload(
        response_type=ResponseType.explanation,
        title=tmpl.name,
        data={"output": output, "rendered_prompt": rendered, "context_preview": context_text[:2000]},
    )
    run = PromptRun(
        template_id=tmpl.id,
        version_id=version.id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        variables_json=req.variables,
        rendered_prompt=rendered,
        output=output,
        eval_scores_json=scores.model_dump(),
        response_payload_json=payload.model_dump(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return RunResponse(
        run_id=run.id,
        rendered_prompt=rendered,
        output=output,
        eval_scores=scores.model_dump(),
        response=payload.model_dump(),
        context_preview=context_text[:2000],
    )


@router.get("/templates/{template_id}/runs", response_model=list[RunResponse])
async def list_runs(
    template_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[RunResponse]:
    await _get_template(db, ctx, template_id)
    res = await db.execute(
        select(PromptRun)
        .where(PromptRun.template_id == template_id, PromptRun.tenant_id == ctx.tenant_id)
        .order_by(PromptRun.created_at.desc())
        .limit(20)
    )
    return [
        RunResponse(
            run_id=r.id,
            rendered_prompt=r.rendered_prompt,
            output=r.output,
            eval_scores=r.eval_scores_json,
            response=r.response_payload_json,
            context_preview=str((r.response_payload_json or {}).get("data", {}).get("context_preview", "")),
        )
        for r in res.scalars().all()
    ]


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    res = await db.execute(
        select(PromptRun, PromptTemplate)
        .join(PromptTemplate, PromptTemplate.id == PromptRun.template_id)
        .where(PromptRun.id == run_id, PromptRun.tenant_id == ctx.tenant_id)
    )
    row = res.first()
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")
    run, tmpl = row
    if run.user_id != ctx.user_id and tmpl.owner_user_id != ctx.user_id:
        raise HTTPException(status_code=403, detail="not allowed to delete this run")
    await db.delete(run)
    await db.commit()
    return {"status": "deleted", "run_id": str(run_id)}


@router.delete("/templates/{template_id}/runs")
async def delete_all_runs(
    template_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | str]:
    tmpl = await _get_template(db, ctx, template_id, owner_only=True)
    result = await db.execute(
        delete(PromptRun).where(
            PromptRun.template_id == tmpl.id,
            PromptRun.tenant_id == ctx.tenant_id,
        )
    )
    await db.commit()
    return {"status": "deleted", "count": result.rowcount or 0}


@router.patch("/templates/{template_id}/share", response_model=TemplateResponse)
async def share_template(
    template_id: uuid.UUID,
    is_shared: bool = Query(default=True),
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> TemplateResponse:
    tmpl = await _get_template(db, ctx, template_id, owner_only=True)
    tmpl.is_shared = is_shared
    await db.commit()
    ver_res = await db.execute(
        select(func.max(PromptVersion.version_number)).where(PromptVersion.template_id == tmpl.id)
    )
    return TemplateResponse(
        id=tmpl.id,
        name=tmpl.name,
        description=tmpl.description,
        bindings_json=tmpl.bindings_json,
        is_shared=tmpl.is_shared,
        is_mine=True,
        owner_user_id=tmpl.owner_user_id,
        latest_version=ver_res.scalar_one(),
    )


@router.post("/runs/{run_id}/pin")
async def pin_run_to_dashboard(
    run_id: uuid.UUID,
    req: PinRunRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    res = await db.execute(
        select(PromptRun).where(PromptRun.id == run_id, PromptRun.tenant_id == ctx.tenant_id)
    )
    run = res.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    card = DashboardCard(
        dashboard_id=req.dashboard_id,
        tenant_id=ctx.tenant_id,
        title=req.title or "Prompt output",
        card_type="explanation",
        layout_json={"x": 0, "y": 0, "cols": 6, "rows": 4},
        refresh_mode=req.refresh_mode,
        source_type="prompt",
        source_config_json={
            "template_id": str(run.template_id),
            "version_id": str(run.version_id),
            "variables": run.variables_json,
        },
        snapshot_response_json=run.response_payload_json,
    )
    db.add(card)
    await db.commit()
    return {"card_id": str(card.id)}


async def _get_template(
    db: AsyncSession,
    ctx: RequestContext,
    template_id: uuid.UUID,
    *,
    owner_only: bool = False,
) -> PromptTemplate:
    res = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.tenant_id == ctx.tenant_id,
        )
    )
    tmpl = res.scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="template not found")
    if owner_only and tmpl.owner_user_id != ctx.user_id:
        raise HTTPException(status_code=403, detail="not template owner")
    if not owner_only and tmpl.owner_user_id != ctx.user_id and not tmpl.is_shared:
        raise HTTPException(status_code=403, detail="template not accessible")
    return tmpl


async def _get_version(
    db: AsyncSession, template_id: uuid.UUID, version_id: uuid.UUID | None
) -> PromptVersion:
    if version_id:
        res = await db.execute(
            select(PromptVersion).where(
                PromptVersion.id == version_id, PromptVersion.template_id == template_id
            )
        )
        version = res.scalar_one_or_none()
    else:
        res = await db.execute(
            select(PromptVersion)
            .where(PromptVersion.template_id == template_id)
            .order_by(PromptVersion.version_number.desc())
            .limit(1)
        )
        version = res.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    return version


def _version_response(v: PromptVersion) -> VersionResponse:
    return VersionResponse(
        id=v.id,
        version_number=v.version_number,
        template_body=v.template_body,
        system_prompt=v.system_prompt,
        variables_schema_json=v.variables_schema_json,
        created_at=v.created_at.isoformat(),
    )
