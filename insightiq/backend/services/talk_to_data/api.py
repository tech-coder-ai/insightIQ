from __future__ import annotations

import csv
import io
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.data.connectors.base import IDBConnector
from core.data.runner import open_connector
from core.data.schema import SchemaMetadata
from core.data.scope import (
    apply_selected_scope,
    scope_counts,
    scope_to_storage,
)
from core.data.sql_schema_check import validate_sql_against_schema
from core.data.validators.readonly import check_readonly_select
from core.chat_history import load_llm_history
from core.deps import get_db
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.models import ChatMessage, Conversation, DataSource
from core.prompts.access import load_accessible_template
from core.request_context import RequestContext, require_auth, require_role
from core.response.classifier import classify_and_format
from core.response.display import chart_date_sql_rules
from core.response.formatter import format_explanation
from core.response.types import ResponsePayload
from core.types import Role

router = APIRouter(prefix="/talk-to-data", tags=["talk-to-data"])

_MAX_SQL_RETRIES = 3

_SQL_GUARDRAILS = """Security guardrails (mandatory — never violate):
- Output ONLY one read-only SELECT query (WITH ... SELECT is allowed).
- NEVER generate INSERT, UPDATE, DELETE, DROP, TRUNCATE, MERGE, CALL, ALTER, GRANT, REVOKE, CREATE, or REPLACE.
- NEVER use multiple statements, semicolons, or any data-mutating operation.
- Do not invoke procedures, COPY TO/FROM, EXEC, or DDL/DML of any kind.
- Use only tables and columns from the schema below."""

SUPPORTED_DB_TYPES = {
    "postgres",
    "s3_object_store",
    "duckdb_files",
    "mssql",
    "oracle",
    "snowflake",
    "hive",
    "bigquery",
}
DIALECT_BY_DB_TYPE = {
    "postgres": "postgres",
    "s3_object_store": "duckdb",
    "duckdb_files": "duckdb",
    "mssql": "tsql",
    "oracle": "oracle",
    "snowflake": "snowflake",
    "hive": "hiveql",
    "bigquery": "bigquery",
}

GLOSSARY_STATUSES = {"draft", "pending", "approved"}
ALLOWED_UPLOAD_SUFFIXES = {".csv", ".parquet", ".pq"}


class SelectedScope(BaseModel):
    tables: dict[str, list[str]] = Field(default_factory=dict)


class PreviewSchemaRequest(BaseModel):
    db_type: str
    connection: dict[str, Any] = Field(default_factory=dict)


class RegisterDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    db_type: str
    connection: dict[str, Any]
    description: str = ""
    selected_scope: SelectedScope | None = None


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str
    dialect: str
    description: str = ""
    metadata_status: str = "draft"
    selected_table_count: int = 0
    selected_column_count: int = 0


class DataSourceDetail(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str
    dialect: str
    description: str = ""
    metadata_status: str = "draft"
    schema_metadata: SchemaMetadata
    selected_scope: SelectedScope
    relationships: list["Relationship"]
    glossary: list["GlossaryEntry"]


class UpdateDataSourceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class SaveScopeRequest(BaseModel):
    selected_scope: SelectedScope


class Relationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    source: str = "manual"  # "introspected" | "manual"


class GlossaryEntry(BaseModel):
    id: str
    table: str
    column: str | None = None
    definition: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "draft"  # draft | pending | approved
    source: str = "manual"  # manual | llm | bulk
    updated_by: str | None = None
    updated_at: str | None = None


class GenerateGlossaryRequest(BaseModel):
    tables: list[str] = Field(default_factory=list)
    context: str = ""


class ApproveGlossaryRequest(BaseModel):
    ids: list[str] | None = None
    all: bool = False
    table: str | None = None


class GenerateDescriptionRequest(BaseModel):
    context: str = ""


class DescriptionResponse(BaseModel):
    description: str


class AskRequest(BaseModel):
    datasource_id: uuid.UUID
    question: str = Field(min_length=1)
    conversation_id: uuid.UUID | None = None
    prompt_template_id: uuid.UUID | None = None


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    sql: str = ""
    response: ResponsePayload
    clarification: str | None = None
    awaiting_confirmation: bool = False
    proposed_sql: str | None = None
    interpretation: str | None = None


@dataclass
class SqlProposal:
    interpretation: str
    sql: str
    original_question: str = ""


@dataclass
class SqlResolution:
    sql: str | None = None
    clarification: str | None = None
    proposal: SqlProposal | None = None


@router.post("/sources/preview-schema", response_model=SchemaMetadata)
async def preview_schema(
    req: PreviewSchemaRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
) -> SchemaMetadata:
    if req.db_type not in SUPPORTED_DB_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported db_type: {req.db_type}")
    if req.db_type == "duckdb_files":
        raise HTTPException(status_code=400, detail="use /sources/preview-schema/upload for file uploads")

    try:
        async with open_connector(req.db_type, req.connection) as connector:
            if not await connector.test_connection():
                raise HTTPException(status_code=400, detail="connection failed")
            return await connector.introspect_schema()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - report failure rather than 500
        raise HTTPException(status_code=400, detail=f"could not introspect schema: {exc}") from exc


@router.post("/sources/preview-schema/upload", response_model=SchemaMetadata)
async def preview_schema_upload(
    table_name: str = Form("data"),
    file: UploadFile = File(...),
    ctx: RequestContext = Depends(require_role(Role.editor)),
) -> SchemaMetadata:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type '{suffix or 'unknown'}'. Allowed: CSV, Parquet.",
        )

    logical_table = _sanitize_identifier(table_name) or "data"
    settings = get_settings_resolver().resolve()
    temp_dir = Path(settings.storage.upload_dir) / str(ctx.tenant_id) / "_preview"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid.uuid4()}{suffix}"
    try:
        with temp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        connection = {"files": {logical_table: str(temp_path)}}
        async with open_connector("duckdb_files", connection) as connector:
            return await connector.introspect_schema()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"could not read file: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/sources", response_model=DataSourceResponse)
async def register_source(
    req: RegisterDataSourceRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    if req.db_type not in SUPPORTED_DB_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported db_type: {req.db_type}")

    async with open_connector(req.db_type, req.connection) as connector:
        if not await connector.test_connection():
            raise HTTPException(status_code=400, detail="connection failed")
        schema = await connector.introspect_schema()

    try:
        scope_payload = scope_to_storage(
            req.selected_scope.model_dump() if req.selected_scope else None,
            schema,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ds = DataSource(
        tenant_id=ctx.tenant_id,
        name=req.name,
        db_type=req.db_type,
        dialect=DIALECT_BY_DB_TYPE[req.db_type],
        description=req.description,
        connection_config_json=req.connection,
        schema_snapshot_json=schema.model_dump(),
        selected_scope_json=scope_payload,
        relationships_json=[r.model_dump() for r in schema.relationships],
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return _to_response(ds)


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_sources(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DataSourceResponse]:
    res = await db.execute(select(DataSource).where(DataSource.tenant_id == ctx.tenant_id))
    return [_to_response(ds) for ds in res.scalars().all()]


@router.post("/sources/upload", response_model=DataSourceResponse)
async def upload_file_source(
    name: str = Form(...),
    table_name: str = Form("data"),
    description: str = Form(""),
    selected_scope_json: str = Form(""),
    file: UploadFile = File(...),
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    """Create a file-backed (DuckDB) datasource from an uploaded CSV/Parquet file."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type '{suffix or 'unknown'}'. Allowed: CSV, Parquet.",
        )

    logical_table = _sanitize_identifier(table_name) or "data"

    settings = get_settings_resolver().resolve()
    upload_dir = Path(settings.storage.upload_dir) / str(ctx.tenant_id) / "datasources"
    upload_dir.mkdir(parents=True, exist_ok=True)

    source_id = uuid.uuid4()
    dest = upload_dir / f"{source_id}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    connection = {"files": {logical_table: str(dest)}}
    try:
        async with open_connector("duckdb_files", connection) as connector:
            schema = await connector.introspect_schema()
    except Exception as exc:  # noqa: BLE001 - surface parse errors to the user
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"could not read file: {exc}") from exc

    raw_scope: dict[str, Any] | None = None
    if selected_scope_json.strip():
        try:
            raw_scope = json.loads(selected_scope_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="selected_scope_json must be valid JSON") from exc
    try:
        scope_payload = scope_to_storage(raw_scope, schema)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ds = DataSource(
        id=source_id,
        tenant_id=ctx.tenant_id,
        name=name,
        db_type="duckdb_files",
        dialect=DIALECT_BY_DB_TYPE["duckdb_files"],
        description=description,
        connection_config_json=connection,
        schema_snapshot_json=schema.model_dump(),
        selected_scope_json=scope_payload,
        relationships_json=[r.model_dump() for r in schema.relationships],
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return _to_response(ds)


@router.get("/sources/{datasource_id}", response_model=DataSourceDetail)
async def get_source(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> DataSourceDetail:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    schema = _full_schema(ds)
    selected_scope = SelectedScope.model_validate(ds.selected_scope_json or {"tables": {}})
    return DataSourceDetail(
        id=ds.id,
        name=ds.name,
        db_type=ds.db_type,
        dialect=ds.dialect,
        description=ds.description or "",
        metadata_status=ds.metadata_status or "draft",
        schema_metadata=schema,
        selected_scope=selected_scope,
        relationships=[Relationship.model_validate(r) for r in (ds.relationships_json or [])],
        glossary=_load_glossary(ds),
    )


@router.patch("/sources/{datasource_id}", response_model=DataSourceResponse)
async def update_source(
    datasource_id: uuid.UUID,
    req: UpdateDataSourceRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    if req.name is not None:
        ds.name = req.name
    if req.description is not None:
        ds.description = req.description
    await db.commit()
    await db.refresh(ds)
    return _to_response(ds)


@router.post("/sources/{datasource_id}/test")
async def test_source(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    try:
        async with open_connector(ds.db_type, ds.connection_config_json) as connector:
            ok = await connector.test_connection()
    except Exception as exc:  # noqa: BLE001 - report failure rather than 500
        raise HTTPException(status_code=400, detail=f"connection failed: {exc}") from exc
    if not ok:
        raise HTTPException(status_code=400, detail="connection failed")
    return {"ok": True}


@router.put("/sources/{datasource_id}/scope", response_model=SelectedScope)
async def save_scope(
    datasource_id: uuid.UUID,
    req: SaveScopeRequest,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> SelectedScope:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    schema = _full_schema(ds)
    try:
        scope_payload = scope_to_storage(req.selected_scope.model_dump(), schema)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ds.selected_scope_json = scope_payload
    await db.commit()
    return SelectedScope.model_validate(scope_payload)


@router.delete("/sources/{datasource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> None:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)

    # Clean up any uploaded files backing a file-based source.
    files = (ds.connection_config_json or {}).get("files", {})
    if isinstance(files, dict):
        for path in files.values():
            try:
                Path(str(path)).unlink(missing_ok=True)
            except OSError:
                pass

    await db.delete(ds)
    await db.commit()


@router.get("/sources/{datasource_id}/schema", response_model=SchemaMetadata)
async def get_schema(
    datasource_id: uuid.UUID,
    refresh: bool = False,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> SchemaMetadata:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    if not refresh and ds.schema_snapshot_json:
        return SchemaMetadata.model_validate(ds.schema_snapshot_json)

    async with open_connector(ds.db_type, ds.connection_config_json) as connector:
        schema = await connector.introspect_schema()
    ds.schema_snapshot_json = schema.model_dump()
    # Merge freshly introspected relationships with any manual ones already saved.
    if schema.relationships:
        existing = [Relationship.model_validate(r) for r in (ds.relationships_json or [])]
        manual = [r for r in existing if r.source != "introspected"]
        introspected = [Relationship(**r.model_dump()) for r in schema.relationships]
        ds.relationships_json = [r.model_dump() for r in (introspected + manual)]
    await db.commit()
    return schema


@router.put("/sources/{datasource_id}/relationships", response_model=list[Relationship])
async def save_relationships(
    datasource_id: uuid.UUID,
    relationships: list[Relationship],
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> list[Relationship]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    ds.relationships_json = [r.model_dump() for r in relationships]
    await db.commit()
    return relationships


@router.get("/sources/{datasource_id}/relationships", response_model=list[Relationship])
async def get_relationships(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[Relationship]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    return [Relationship.model_validate(r) for r in (ds.relationships_json or [])]


@router.get("/sources/{datasource_id}/glossary", response_model=list[GlossaryEntry])
async def get_glossary(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryEntry]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    return _load_glossary(ds)


@router.put("/sources/{datasource_id}/glossary", response_model=list[GlossaryEntry])
async def save_glossary(
    datasource_id: uuid.UUID,
    entries: list[GlossaryEntry],
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryEntry]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    now = _now_iso()
    for e in entries:
        if e.status not in GLOSSARY_STATUSES:
            e.status = "draft"
        e.updated_by = str(ctx.user_id)
        e.updated_at = now
    ds.glossary_json = [e.model_dump() for e in entries]
    ds.metadata_status = _rollup_status(entries)
    await db.commit()
    return entries


@router.post("/sources/{datasource_id}/glossary/generate", response_model=list[GlossaryEntry])
async def generate_glossary(
    datasource_id: uuid.UUID,
    req: GenerateGlossaryRequest | None = None,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryEntry]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    schema = SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})
    req = req or GenerateGlossaryRequest()
    selected = set(req.tables) if req.tables else None

    new_entries = await _generate_glossary(schema, selected, req.context, ds.name)

    # Preserve already-approved entries; replace the rest for selected tables.
    existing = _load_glossary(ds)
    preserved = [
        e
        for e in existing
        if e.status == "approved" or (selected is not None and e.table not in selected)
    ]
    preserved_ids = {e.id for e in preserved}
    merged = preserved + [e for e in new_entries if e.id not in preserved_ids]

    now = _now_iso()
    for e in merged:
        if e.updated_at is None:
            e.updated_at = now
            e.updated_by = str(ctx.user_id)
    ds.glossary_json = [e.model_dump() for e in merged]
    ds.metadata_status = _rollup_status(merged)
    await db.commit()
    return merged


@router.post("/sources/{datasource_id}/glossary/upload", response_model=list[GlossaryEntry])
async def upload_glossary(
    datasource_id: uuid.UUID,
    file: UploadFile = File(...),
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryEntry]:
    """Bulk-upload glossary entries from a CSV with columns: table, column, definition, tags."""
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="empty or invalid CSV")

    fields = {(f or "").strip().lower(): f for f in reader.fieldnames}
    if "table" not in fields:
        raise HTTPException(status_code=400, detail="CSV must include a 'table' column header")

    now = _now_iso()
    uploaded: dict[str, GlossaryEntry] = {}
    for row in reader:
        table = (row.get(fields["table"], "") or "").strip()
        if not table:
            continue
        column = (row.get(fields.get("column", "column"), "") or "").strip() or None
        definition = (row.get(fields.get("definition", "definition"), "") or "").strip()
        tags_raw = (row.get(fields.get("tags", "tags"), "") or "").strip()
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]
        entry_id = _glossary_id(table, column)
        uploaded[entry_id] = GlossaryEntry(
            id=entry_id,
            table=table,
            column=column,
            definition=definition,
            tags=tags,
            status="pending",
            source="bulk",
            updated_by=str(ctx.user_id),
            updated_at=now,
        )

    if not uploaded:
        raise HTTPException(status_code=400, detail="no valid rows found in CSV")

    existing = _load_glossary(ds)
    merged_map: dict[str, GlossaryEntry] = {e.id: e for e in existing}
    for entry_id, entry in uploaded.items():
        merged_map[entry_id] = entry
    merged = list(merged_map.values())
    ds.glossary_json = [e.model_dump() for e in merged]
    ds.metadata_status = _rollup_status(merged)
    await db.commit()
    return merged


@router.post("/sources/{datasource_id}/glossary/approve", response_model=list[GlossaryEntry])
async def approve_glossary(
    datasource_id: uuid.UUID,
    req: ApproveGlossaryRequest,
    ctx: RequestContext = Depends(require_role(Role.admin)),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryEntry]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    entries = _load_glossary(ds)
    target_ids = set(req.ids or [])
    now = _now_iso()
    for e in entries:
        match = (
            req.all
            or e.id in target_ids
            or (req.table is not None and e.table == req.table)
        )
        if match and e.status != "approved":
            e.status = "approved"
            e.updated_by = str(ctx.user_id)
            e.updated_at = now
    ds.glossary_json = [e.model_dump() for e in entries]
    ds.metadata_status = _rollup_status(entries)
    await db.commit()
    return entries


@router.post("/sources/{datasource_id}/description/generate", response_model=DescriptionResponse)
async def generate_description(
    datasource_id: uuid.UUID,
    req: GenerateDescriptionRequest | None = None,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> DescriptionResponse:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    schema = _scoped_schema(ds)
    req = req or GenerateDescriptionRequest()
    description = await _generate_description(ds.name, ds.db_type, schema, req.context)
    return DescriptionResponse(description=description)


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    ds = await _get_datasource(db, ctx.tenant_id, req.datasource_id)
    conversation_id = req.conversation_id or uuid.uuid4()
    await _ensure_conversation(db, ctx, conversation_id, ds.id, req.question)

    prior_history: list[LLMMessage] = []
    if req.conversation_id:
        prior_history = await load_llm_history(db, ctx, req.conversation_id)

    schema = _scoped_schema(ds)
    relationships = [
        Relationship.model_validate(r)
        for r in (ds.relationships_json or [])
        if _relationship_in_schema(r, schema)
    ]
    glossary = [
        e
        for e in _load_glossary(ds)
        if e.status == "approved" and _glossary_in_schema(e, schema)
    ]
    system_prompt = _build_sql_system_prompt(
        ds.dialect, schema, relationships, glossary, question=req.question
    )
    if req.prompt_template_id:
        _tmpl, version = await load_accessible_template(db, ctx, req.prompt_template_id)
        extras: list[str] = []
        if version.system_prompt.strip():
            extras.append(f"Analyst instructions:\n{version.system_prompt.strip()}")
        if version.template_body.strip():
            extras.append(f"Response formatting instructions:\n{version.template_body.strip()}")
        if extras:
            system_prompt = f"{system_prompt}\n\n" + "\n\n".join(extras)

    async with open_connector(ds.db_type, ds.connection_config_json) as connector:
        if req.conversation_id and _is_affirmative(req.question):
            pending = await _get_pending_proposal(db, ctx, req.conversation_id)
            if pending:
                return await _execute_confirmed_proposal(
                    db,
                    ctx=ctx,
                    ds=ds,
                    schema=schema,
                    connector=connector,
                    conversation_id=req.conversation_id,
                    question=req.question,
                    pending=pending,
                )

        if req.conversation_id and _is_negative(req.question):
            pending = await _get_pending_proposal(db, ctx, req.conversation_id)
            if pending:
                message = "No problem — rephrase your question with the table and metric you want."
                response = format_explanation(output=message, title=pending.get("original_question") or req.question)
                await _persist_ask_messages(
                    db,
                    ctx=ctx,
                    conversation_id=req.conversation_id,
                    datasource_id=ds.id,
                    question=req.question,
                    sql="",
                    response=response,
                    awaiting_confirmation=False,
                )
                return AskResponse(
                    conversation_id=req.conversation_id,
                    sql="",
                    response=response,
                    clarification=message,
                )

        resolution = await _resolve_sql_or_clarify(
            dialect=ds.dialect,
            schema=schema,
            system_prompt=system_prompt,
            question=req.question,
            connector=connector,
            prior_messages=prior_history,
        )

        if resolution.proposal:
            return await _return_sql_proposal(
                db,
                ctx=ctx,
                ds=ds,
                connector=connector,
                schema=schema,
                conversation_id=conversation_id,
                question=req.question,
                proposal=resolution.proposal,
            )

        if resolution.clarification:
            proposal = await _build_sql_proposal(
                dialect=ds.dialect,
                schema=schema,
                question=req.question,
                connector=connector,
                context=resolution.clarification,
            )
            if proposal:
                return await _return_sql_proposal(
                    db,
                    ctx=ctx,
                    ds=ds,
                    connector=connector,
                    schema=schema,
                    conversation_id=conversation_id,
                    question=req.question,
                    proposal=proposal,
                )
            response = format_explanation(output=resolution.clarification, title=req.question)
            await _persist_ask_messages(
                db,
                ctx=ctx,
                conversation_id=conversation_id,
                datasource_id=ds.id,
                question=req.question,
                sql="",
                response=response,
            )
            return AskResponse(
                conversation_id=conversation_id,
                sql="",
                response=response,
                clarification=resolution.clarification,
            )

        sql = resolution.sql or ""
        if not sql:
            proposal = await _build_sql_proposal(
                dialect=ds.dialect,
                schema=schema,
                question=req.question,
                connector=connector,
            )
            if proposal:
                return await _return_sql_proposal(
                    db,
                    ctx=ctx,
                    ds=ds,
                    connector=connector,
                    schema=schema,
                    conversation_id=conversation_id,
                    question=req.question,
                    proposal=proposal,
                )
            message = (
                "I couldn't build a valid query from that question using the available schema. "
                "Try naming the table or metric you want."
            )
            response = format_explanation(output=message, title=req.question)
            await _persist_ask_messages(
                db,
                ctx=ctx,
                conversation_id=conversation_id,
                datasource_id=ds.id,
                question=req.question,
                sql="",
                response=response,
            )
            return AskResponse(conversation_id=conversation_id, sql="", response=response, clarification=message)

        confirm = await _maybe_require_confirmation(req.question, sql, schema, ds.dialect)
        if confirm:
            return await _return_sql_proposal(
                db,
                ctx=ctx,
                ds=ds,
                connector=connector,
                schema=schema,
                conversation_id=conversation_id,
                question=req.question,
                proposal=confirm,
            )

        try:
            result = await connector.execute_query(sql)
        except Exception as exc:  # noqa: BLE001 - return proposal or clarification instead of 500
            proposal = await _build_sql_proposal(
                dialect=ds.dialect,
                schema=schema,
                question=req.question,
                connector=connector,
                context=str(exc),
                draft_sql=sql,
            )
            if proposal:
                return await _return_sql_proposal(
                    db,
                    ctx=ctx,
                    ds=ds,
                    connector=connector,
                    schema=schema,
                    conversation_id=conversation_id,
                    question=req.question,
                    proposal=proposal,
                )
            message = await _execution_failure_clarification(req.question, schema, sql, str(exc))
            response = format_explanation(output=message, title=req.question)
            await _persist_ask_messages(
                db,
                ctx=ctx,
                conversation_id=conversation_id,
                datasource_id=ds.id,
                question=req.question,
                sql=sql,
                response=response,
            )
            return AskResponse(conversation_id=conversation_id, sql=sql, response=response, clarification=message)

        response = classify_and_format(result, question=req.question)
        await _persist_ask_messages(
            db,
            ctx=ctx,
            conversation_id=conversation_id,
            datasource_id=ds.id,
            question=req.question,
            sql=sql,
            response=response,
        )
        return AskResponse(conversation_id=conversation_id, sql=sql, response=response)


async def _persist_ask_messages(
    db: AsyncSession,
    *,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    datasource_id: uuid.UUID,
    question: str,
    sql: str,
    response: ResponsePayload,
    awaiting_confirmation: bool = False,
    pending_sql: str | None = None,
    pending_interpretation: str | None = None,
    pending_original_question: str | None = None,
) -> None:
    assistant_meta: dict[str, Any] = {
        "response": response.model_dump(mode="json"),
        "sql": sql or None,
        "awaiting_confirmation": awaiting_confirmation,
    }
    if awaiting_confirmation and pending_sql:
        assistant_meta["pending_sql"] = pending_sql
        assistant_meta["pending_interpretation"] = pending_interpretation or ""
        assistant_meta["pending_original_question"] = pending_original_question or question

    db.add(
        ChatMessage(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation_id=conversation_id,
            role="user",
            content=question,
            metadata_json={"datasource_id": str(datasource_id)},
        )
    )
    db.add(
        ChatMessage(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=sql or str(response.data.get("output", "")),
            metadata_json=assistant_meta,
        )
    )
    await db.commit()


def _sanitize_identifier(value: str) -> str:
    """Reduce a user-supplied table name to a safe SQL identifier."""
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in value.strip().lower())
    cleaned = cleaned.strip("_")
    if cleaned and cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:63]


def _full_schema(ds: DataSource) -> SchemaMetadata:
    return SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})


def _scoped_schema(ds: DataSource) -> SchemaMetadata:
    return apply_selected_scope(_full_schema(ds), ds.selected_scope_json or None)


def _relationship_in_schema(raw: dict[str, Any] | Relationship, schema: SchemaMetadata) -> bool:
    rel = raw if isinstance(raw, Relationship) else Relationship.model_validate(raw)
    cols = {(t.name, c.name) for t in schema.tables for c in t.columns}
    return (rel.from_table, rel.from_column) in cols and (rel.to_table, rel.to_column) in cols


def _glossary_in_schema(entry: GlossaryEntry, schema: SchemaMetadata) -> bool:
    table = schema.tables and next((t for t in schema.tables if t.name == entry.table), None)
    if table is None:
        return False
    if entry.column is None:
        return True
    return any(c.name == entry.column for c in table.columns)


def _to_response(ds: DataSource) -> DataSourceResponse:
    table_count, column_count = scope_counts(ds.schema_snapshot_json, ds.selected_scope_json)
    return DataSourceResponse(
        id=ds.id,
        name=ds.name,
        db_type=ds.db_type,
        dialect=ds.dialect,
        description=ds.description or "",
        metadata_status=ds.metadata_status or "draft",
        selected_table_count=table_count,
        selected_column_count=column_count,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _glossary_id(table: str, column: str | None) -> str:
    return f"{table}::{column}" if column else f"{table}::"


def _load_glossary(ds: DataSource) -> list[GlossaryEntry]:
    """Load glossary entries, tolerating the legacy term/definition shape."""
    out: list[GlossaryEntry] = []
    seen: set[str] = set()
    for raw in ds.glossary_json or []:
        if not isinstance(raw, dict):
            continue
        if "id" in raw and "table" in raw:
            try:
                entry = GlossaryEntry.model_validate(raw)
            except Exception:  # noqa: BLE001 - skip malformed rows
                continue
        else:
            # Legacy shape: {term, definition, table, column}
            table = raw.get("table") or raw.get("term") or "unknown"
            column = raw.get("column")
            entry = GlossaryEntry(
                id=_glossary_id(table, column),
                table=table,
                column=column,
                definition=raw.get("definition", ""),
                status="draft",
                source="manual",
            )
        if entry.id in seen:
            continue
        seen.add(entry.id)
        out.append(entry)
    return out


def _rollup_status(entries: list[GlossaryEntry]) -> str:
    if not entries:
        return "draft"
    statuses = {e.status for e in entries}
    if statuses == {"approved"}:
        return "approved"
    if "approved" in statuses:
        return "partially_approved"
    return "draft"


def _build_sql_system_prompt(
    dialect: str,
    schema: SchemaMetadata,
    relationships: list[Relationship],
    glossary: list[GlossaryEntry],
    *,
    question: str = "",
) -> str:
    table_lines = []
    for table in schema.tables:
        col_parts = []
        for c in table.columns:
            hints = [c.data_type]
            if c.is_primary_key:
                hints.append("PK")
            if c.is_indexed and not c.is_primary_key:
                hints.append("indexed")
            col_parts.append(f"{c.name} ({', '.join(hints)})")
        table_lines.append(f"- table: {table.name}\n  columns: {', '.join(col_parts)}")
    rel_lines = [
        f"- {r.from_table}.{r.from_column} -> {r.to_table}.{r.to_column}"
        for r in relationships
    ]
    glossary_lines = []
    for g in glossary[:40]:
        target = f"{g.table}.{g.column}" if g.column else g.table
        tag_suffix = f" [tags: {', '.join(g.tags)}]" if g.tags else ""
        glossary_lines.append(f"- {target}: {g.definition}{tag_suffix}")
    return (
        f"You are an expert {dialect} analyst. Convert the user's question into SQL against the schema below.\n\n"
        f"{_SQL_GUARDRAILS}\n\n"
        "Query rules:\n"
        "- Output ONLY the SQL text. No markdown fences, no explanation, no trailing semicolon.\n"
        "- Use ONLY tables and columns listed in the schema below. Never invent table or column names.\n"
        "- If the question refers to a business term not in the schema (e.g. 'cost' when only 'amount' exists), "
        "map to the closest available column or ask the user.\n"
        "- If the question is ambiguous or missing required detail (metric, date range, table, filter), "
        "respond with exactly one line: CLARIFY: <your best guess at what the user wants, referencing schema columns>\n"
        "- Prefer explicit column lists over SELECT * when aggregating or charting.\n"
        "- Honor requested row limits (e.g. top 10 → LIMIT 10).\n"
        "- Use JOINs when relationships are provided.\n"
        f"{chart_date_sql_rules(dialect, question)}\n\n"
        "Schema:\n" + ("\n".join(table_lines) or "- table: unknown") + "\n\n"
        "Relationships:\n" + ("\n".join(rel_lines) or "- none") + "\n\n"
        "Glossary:\n" + ("\n".join(glossary_lines) or "- none")
    )


_AFFIRMATIVE = re.compile(
    r"^(?:yes|y|yeah|yep|yup|correct|right|that's right|that is right|run it|go ahead|"
    r"confirm|confirmed|ok|okay|sure|do it|proceed|sounds good|please do|exactly)\.?$",
    re.IGNORECASE,
)
_NEGATIVE = re.compile(
    r"^(?:no|n|nope|cancel|wrong|not that|try again|don't|do not)\.?$",
    re.IGNORECASE,
)


def _is_affirmative(text: str) -> bool:
    return bool(_AFFIRMATIVE.match(text.strip()))


def _is_negative(text: str) -> bool:
    return bool(_NEGATIVE.match(text.strip()))


async def _get_pending_proposal(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
) -> dict[str, str] | None:
    res = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.tenant_id == ctx.tenant_id,
            ChatMessage.role == "assistant",
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(1)
    )
    msg = res.scalar_one_or_none()
    if msg is None:
        return None
    meta = msg.metadata_json or {}
    if meta.get("awaiting_confirmation") and meta.get("pending_sql"):
        return {
            "sql": str(meta["pending_sql"]),
            "interpretation": str(meta.get("pending_interpretation") or ""),
            "original_question": str(meta.get("pending_original_question") or ""),
        }
    return None


async def _validate_sql_ready(
    sql: str,
    schema: SchemaMetadata,
    connector: IDBConnector,
) -> str | None:
    guard = check_readonly_select(sql)
    if not guard.ok:
        return guard.error or "read-only guard rejected query"
    schema_check = validate_sql_against_schema(sql, schema)
    if not schema_check.ok:
        return schema_check.error or "schema check failed"
    validation = await connector.validate_sql(sql)
    if not validation.ok:
        return validation.error or "invalid SQL"
    return None


def _proposal_message(proposal: SqlProposal) -> str:
    return (
        f"I think you're asking for: {proposal.interpretation}\n\n"
        "Does that look right? Reply yes to run the query, or no to rephrase."
    )


async def _return_sql_proposal(
    db: AsyncSession,
    *,
    ctx: RequestContext,
    ds: DataSource,
    connector: IDBConnector,
    schema: SchemaMetadata,
    conversation_id: uuid.UUID,
    question: str,
    proposal: SqlProposal,
) -> AskResponse:
    proposal.original_question = proposal.original_question or question
    err = await _validate_sql_ready(proposal.sql, schema, connector)
    if err:
        rebuilt = await _build_sql_proposal(
            dialect=ds.dialect,
            schema=schema,
            question=proposal.original_question,
            connector=connector,
            context=err,
            draft_sql=proposal.sql,
        )
        if rebuilt:
            proposal = rebuilt
        else:
            response = format_explanation(output=f"I couldn't validate a query yet: {err}", title=question)
            await _persist_ask_messages(
                db,
                ctx=ctx,
                conversation_id=conversation_id,
                datasource_id=ds.id,
                question=question,
                sql="",
                response=response,
            )
            return AskResponse(
                conversation_id=conversation_id,
                sql="",
                response=response,
                clarification=str(err),
            )

    message = _proposal_message(proposal)
    response = format_explanation(output=message, title=question)
    response.data["interpretation"] = proposal.interpretation
    response.data["proposed_sql"] = proposal.sql
    response.data["awaiting_confirmation"] = True

    await _persist_ask_messages(
        db,
        ctx=ctx,
        conversation_id=conversation_id,
        datasource_id=ds.id,
        question=question,
        sql="",
        response=response,
        awaiting_confirmation=True,
        pending_sql=proposal.sql,
        pending_interpretation=proposal.interpretation,
        pending_original_question=proposal.original_question,
    )
    return AskResponse(
        conversation_id=conversation_id,
        sql="",
        response=response,
        awaiting_confirmation=True,
        proposed_sql=proposal.sql,
        interpretation=proposal.interpretation,
    )


async def _execute_confirmed_proposal(
    db: AsyncSession,
    *,
    ctx: RequestContext,
    ds: DataSource,
    schema: SchemaMetadata,
    connector: IDBConnector,
    conversation_id: uuid.UUID,
    question: str,
    pending: dict[str, str],
) -> AskResponse:
    sql = pending["sql"]
    original_question = pending.get("original_question") or question
    err = await _validate_sql_ready(sql, schema, connector)
    if err:
        message = f"I couldn't run that query: {err}. Please ask again with more detail."
        response = format_explanation(output=message, title=original_question)
        await _persist_ask_messages(
            db,
            ctx=ctx,
            conversation_id=conversation_id,
            datasource_id=ds.id,
            question=question,
            sql=sql,
            response=response,
            awaiting_confirmation=False,
        )
        return AskResponse(conversation_id=conversation_id, sql=sql, response=response, clarification=message)

    try:
        result = await connector.execute_query(sql)
    except Exception as exc:  # noqa: BLE001
        message = await _execution_failure_clarification(original_question, schema, sql, str(exc))
        response = format_explanation(output=message, title=original_question)
        await _persist_ask_messages(
            db,
            ctx=ctx,
            conversation_id=conversation_id,
            datasource_id=ds.id,
            question=question,
            sql=sql,
            response=response,
        )
        return AskResponse(conversation_id=conversation_id, sql=sql, response=response, clarification=message)

    response = classify_and_format(result, question=original_question)
    await _persist_ask_messages(
        db,
        ctx=ctx,
        conversation_id=conversation_id,
        datasource_id=ds.id,
        question=question,
        sql=sql,
        response=response,
        awaiting_confirmation=False,
    )
    return AskResponse(conversation_id=conversation_id, sql=sql, response=response)


async def _build_sql_proposal(
    *,
    dialect: str,
    schema: SchemaMetadata,
    question: str,
    connector: IDBConnector,
    context: str = "",
    draft_sql: str = "",
) -> SqlProposal | None:
    schema_lines = []
    for table in schema.tables:
        cols = ", ".join(f"{c.name} ({c.data_type})" for c in table.columns)
        schema_lines.append(f"{table.name}: {cols}")

    system = (
        f"You are a {dialect} analyst. Given a user question and schema metadata, infer the most likely intent "
        "and write ONE read-only SELECT using ONLY listed tables and columns. "
        "Map business terms to the closest schema columns (e.g. cost/revenue → amount). "
        f"{chart_date_sql_rules(dialect, question)} "
        "Respond ONLY with JSON (no markdown): "
        '{"interpretation": "plain English summary of what you will query", "sql": "SELECT ..."}'
    )
    user = (
        f"User question: {question}\n"
        f"Schema:\n" + "\n".join(schema_lines) + "\n"
        + (f"Context: {context}\n" if context else "")
        + (f"Draft SQL (fix if needed): {draft_sql}\n" if draft_sql else "")
    )

    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=user)])
        proposal = _parse_proposal_json(raw, original_question=question)
        if proposal and await _validate_sql_ready(proposal.sql, schema, connector) is None:
            return proposal
    except Exception:  # noqa: BLE001
        pass

    if draft_sql:
        err = await _validate_sql_ready(draft_sql, schema, connector)
        if err is None:
            interpretation = context or f"Run a query to answer: {question}"
            return SqlProposal(interpretation=interpretation, sql=draft_sql, original_question=question)
    return None


def _parse_proposal_json(raw: str, *, original_question: str) -> SqlProposal | None:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    interpretation = str(payload.get("interpretation", "")).strip()
    sql = _extract_sql(str(payload.get("sql", "")))
    if interpretation and sql:
        return SqlProposal(interpretation=interpretation, sql=sql, original_question=original_question)
    return None


async def _maybe_require_confirmation(
    question: str,
    sql: str,
    schema: SchemaMetadata,
    dialect: str,
) -> SqlProposal | None:
    """Ask for confirmation when the question uses terms that don't literally match schema columns."""
    schema_terms = {t.name.lower() for t in schema.tables}
    schema_terms.update(c.name.lower() for t in schema.tables for c in t.columns)
    question_tokens = {tok.lower() for tok in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", question)}
    fuzzy_terms = question_tokens - schema_terms - {
        "show",
        "the",
        "a",
        "an",
        "as",
        "by",
        "for",
        "from",
        "in",
        "on",
        "to",
        "and",
        "or",
        "all",
        "top",
        "month",
        "monthly",
        "week",
        "daily",
        "line",
        "bar",
        "chart",
        "graph",
        "plot",
        "trend",
        "list",
        "count",
        "sum",
        "average",
        "total",
        "data",
        "table",
        "rows",
        "me",
        "my",
        "what",
        "how",
        "many",
        "each",
        "per",
        "over",
        "time",
    }
    if not fuzzy_terms:
        return None

    schema_lines = []
    for table in schema.tables:
        cols = ", ".join(c.name for c in table.columns)
        schema_lines.append(f"{table.name}: {cols}")
    system = (
        f"You decide if a {dialect} query should be confirmed with the user before running. "
        "If the question uses business terms that were mapped to schema columns, confirmation is needed. "
        "Respond ONLY with JSON: "
        '{"needs_confirmation": true/false, "interpretation": "what the query will return"}'
    )
    user = (
        f"Question: {question}\n"
        f"Ambiguous terms: {', '.join(sorted(fuzzy_terms))}\n"
        f"Schema:\n" + "\n".join(schema_lines) + f"\nSQL:\n{sql}"
    )
    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=user)])
        payload = _parse_json_object(raw)
        if payload and payload.get("needs_confirmation"):
            interpretation = str(payload.get("interpretation", "")).strip()
            if interpretation:
                return SqlProposal(interpretation=interpretation, sql=sql, original_question=question)
    except Exception:  # noqa: BLE001
        pass

    if fuzzy_terms:
        mapped = ", ".join(sorted(fuzzy_terms))
        return SqlProposal(
            interpretation=f"Answer your question using available schema columns (mapped from: {mapped})",
            sql=sql,
            original_question=question,
        )
    return None


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


async def _resolve_sql_or_clarify(
    *,
    dialect: str,
    schema: SchemaMetadata,
    system_prompt: str,
    question: str,
    connector: IDBConnector,
    prior_messages: list[LLMMessage] | None = None,
    max_retries: int = _MAX_SQL_RETRIES,
) -> SqlResolution:
    """Generate SQL, verify against schema metadata, validate with EXPLAIN, or ask the user."""
    messages = list(prior_messages or [])
    messages.append(LLMMessage(role="user", content=question))
    last_error = ""
    last_sql = ""

    for attempt in range(max_retries):
        raw = await _complete_sql_llm_raw(system_prompt, messages)
        sql, clarify = _parse_llm_sql_response(raw)
        if clarify:
            proposal = await _build_sql_proposal(
                dialect=dialect,
                schema=schema,
                question=question,
                connector=connector,
                context=clarify,
                draft_sql=last_sql,
            )
            if proposal:
                return SqlResolution(proposal=proposal)
            return SqlResolution(clarification=clarify)
        if not sql:
            last_error = "model did not return SQL"
            messages.append(LLMMessage(role="assistant", content=raw))
            messages.append(LLMMessage(role="user", content="Return a single read-only SELECT or CLARIFY: ..."))
            continue

        last_sql = sql
        guard = check_readonly_select(sql)
        if not guard.ok:
            last_error = guard.error or "read-only guard rejected query"
            if attempt >= max_retries - 1:
                break
            messages.extend(_retry_messages(sql, last_error))
            continue

        schema_check = validate_sql_against_schema(sql, schema)
        if not schema_check.ok:
            last_error = schema_check.error or "schema check failed"
            if attempt >= max_retries - 1:
                break
            messages.extend(_retry_messages(sql, f"Schema check failed: {last_error}"))
            continue

        verified = await _verify_sql_with_llm(
            dialect=dialect,
            schema=schema,
            question=question,
            sql=sql,
        )
        if verified.proposal:
            return verified
        if verified.clarification:
            proposal = await _build_sql_proposal(
                dialect=dialect,
                schema=schema,
                question=question,
                connector=connector,
                context=verified.clarification,
                draft_sql=sql,
            )
            if proposal:
                return SqlResolution(proposal=proposal)
            return verified
        if verified.sql:
            sql = verified.sql

        validation = await connector.validate_sql(sql)
        if validation.ok:
            return SqlResolution(sql=sql)

        last_error = validation.error or "invalid SQL"
        if attempt >= max_retries - 1:
            break
        messages.extend(_retry_messages(sql, f"Database validation failed: {last_error}"))

    clarification = await _failure_clarification(question, schema, last_error)
    proposal = await _build_sql_proposal(
        dialect=dialect,
        schema=schema,
        question=question,
        connector=connector,
        context=last_error,
        draft_sql=last_sql,
    )
    if proposal:
        return SqlResolution(proposal=proposal)
    return SqlResolution(clarification=clarification)


def _retry_messages(sql: str, error: str) -> list[LLMMessage]:
    return [
        LLMMessage(role="assistant", content=sql),
        LLMMessage(
            role="user",
            content=(
                f"{error}. "
                "Fix the query using ONLY tables and columns from the schema, "
                "or respond CLARIFY: <question for the user>."
            ),
        ),
    ]


async def _verify_sql_with_llm(
    *,
    dialect: str,
    schema: SchemaMetadata,
    question: str,
    sql: str,
) -> SqlResolution:
    """LLM pass to verify SQL matches schema metadata before execution."""
    schema_lines = []
    for table in schema.tables:
        cols = ", ".join(f"{c.name} ({c.data_type})" for c in table.columns)
        schema_lines.append(f"{table.name}: {cols}")

    system = (
        f"You verify {dialect} SQL against the schema before it runs. "
        "Respond ONLY with JSON (no markdown): "
        '{"action":"run","sql":"..."} if the query is correct (you may fix minor issues), '
        '"action":"fix","sql":"..."} if it must be corrected to use only schema objects, '
        '"action":"propose","interpretation":"...","sql":"..."} if the user should confirm your interpretation, '
        'or {"action":"clarify","message":"..."} if the user must provide missing detail}.'
    )
    user = (
        f"User question: {question}\n\n"
        f"Schema:\n" + "\n".join(schema_lines) + "\n\n"
        f"Proposed SQL:\n{sql}"
    )

    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=user)])
        parsed = _parse_verify_json(raw)
        if parsed is not None:
            return parsed
    except Exception:  # noqa: BLE001 - fall back to static schema check
        pass

    return SqlResolution(sql=sql)


def _parse_verify_json(raw: str) -> SqlResolution | None:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    action = str(payload.get("action", "")).lower()
    if action == "clarify":
        message = str(payload.get("message", "")).strip()
        return SqlResolution(clarification=message) if message else None
    if action == "propose":
        interpretation = str(payload.get("interpretation", "")).strip()
        sql = _extract_sql(str(payload.get("sql", "")))
        if interpretation and sql:
            return SqlResolution(proposal=SqlProposal(interpretation=interpretation, sql=sql))
        return None
    if action in {"run", "fix"}:
        sql = _extract_sql(str(payload.get("sql", "")))
        return SqlResolution(sql=sql) if sql else None
    return None


async def _failure_clarification(question: str, schema: SchemaMetadata, error: str) -> str:
    tables = ", ".join(t.name for t in schema.tables[:8]) or "none"
    prompt = (
        "The user asked a data question but the query could not be validated. "
        "Write one or two friendly sentences asking the user for the missing detail "
        "or suggesting how to rephrase. Do not mention internal errors or stack traces."
    )
    user = f"Question: {question}\nAvailable tables: {tables}\nIssue: {error}"
    try:
        llm = LLMProviderFactory.create("openai")
        text = await llm.complete(system=prompt, messages=[LLMMessage(role="user", content=user)])
        cleaned = text.strip()
        if cleaned:
            return cleaned
    except Exception:  # noqa: BLE001
        pass
    return (
        "I couldn't build a valid query from that question with the current schema. "
        f"Available tables: {tables}. "
        "Which table and metric should I use, and over what time range?"
    )


async def _execution_failure_clarification(
    question: str,
    schema: SchemaMetadata,
    sql: str,
    error: str,
) -> str:
    return await _failure_clarification(
        question,
        schema,
        f"Query failed at execution time. SQL: {sql}. Error: {error}",
    )


async def _generate_sql_with_retries(
    system_prompt: str,
    question: str,
    connector: IDBConnector,
    *,
    schema: SchemaMetadata | None = None,
    dialect: str = "postgres",
    max_retries: int = _MAX_SQL_RETRIES,
) -> tuple[str, str | None]:
    """Generate SQL via LLM, enforce guardrails, validate, retry. Used by tests/helpers."""
    resolution = await _resolve_sql_or_clarify(
        dialect=dialect,
        schema=schema or SchemaMetadata(),
        system_prompt=system_prompt,
        question=question,
        connector=connector,
        max_retries=max_retries,
    )
    if resolution.clarification:
        return "", resolution.clarification
    return resolution.sql or "", "could not generate valid read-only SQL"


async def _complete_sql_llm_raw(system_prompt: str, messages: list[LLMMessage]) -> str:
    """Call OpenAI for NL→SQL; fall back to heuristic when LLM is unavailable."""
    try:
        llm = LLMProviderFactory.create("openai")
        return await llm.complete(system=system_prompt, messages=messages)
    except Exception:  # noqa: BLE001
        pass
    llm = LLMProviderFactory.create("heuristic")
    return await llm.complete(system=system_prompt, messages=messages)


def _parse_llm_sql_response(raw: str) -> tuple[str | None, str | None]:
    text = raw.strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("CLARIFY:"):
            return None, stripped.split(":", 1)[1].strip()
    if text.upper().startswith("CLARIFY:"):
        return None, text.split(":", 1)[1].strip()
    sql = _extract_sql(raw)
    return sql or None, None


async def _complete_sql_llm(system_prompt: str, messages: list[LLMMessage]) -> str:
    raw = await _complete_sql_llm_raw(system_prompt, messages)
    sql, _clarify = _parse_llm_sql_response(raw)
    if sql:
        return sql
    return _extract_sql(raw) or raw.strip().rstrip(";")


async def _generate_sql(system_prompt: str, question: str) -> str:
    """Generate SQL via LLM (single attempt, no validation). Used by tests/helpers."""
    return await _complete_sql_llm(system_prompt, [LLMMessage(role="user", content=question)])


def _extract_sql(raw: str) -> str:
    """Pull a single SELECT statement out of an LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("sql"):
                text = text.lstrip()[3:]
    text = text.strip().rstrip(";")

    # If the model added prose, keep from the first SELECT onward.
    match = re.search(r"(?is)\bselect\b.+", text)
    if match:
        text = match.group(0).strip().rstrip(";")
    return text


async def _generate_glossary(
    schema: SchemaMetadata,
    tables: set[str] | None,
    context: str,
    datasource_name: str,
) -> list[GlossaryEntry]:
    """Generate glossary entries via LLM, falling back to a heuristic generator."""
    target_tables = [t for t in schema.tables if tables is None or t.name in tables]
    try:
        entries = await _generate_glossary_llm(target_tables, context, datasource_name)
        if entries:
            return entries
    except Exception:  # noqa: BLE001 - fall back when LLM unavailable / errors
        pass
    return _generate_glossary_heuristic(target_tables)


async def _generate_glossary_llm(
    tables: list[Any],
    context: str,
    datasource_name: str,
) -> list[GlossaryEntry]:
    schema_lines = []
    for t in tables:
        cols = ", ".join(f"{c.name} ({c.data_type})" for c in t.columns)
        schema_lines.append(f"{t.name}: {cols}")
    system = (
        "You are a data catalog assistant. Given a database schema and optional "
        "business context, write a concise business definition for each table and "
        "each column, and suggest 1-3 short lowercase tags per column "
        "(e.g. pii, identifier, metric, date, foreign_key, status). "
        "Respond ONLY with a JSON array. Each item must have: "
        '"table" (string), "column" (string or null for a table-level entry), '
        '"definition" (string), "tags" (array of strings). '
        "Include one table-level entry (column=null) per table plus one entry per column."
    )
    user = (
        f"Datasource: {datasource_name}\n"
        f"Business context: {context or 'none provided'}\n\n"
        "Schema:\n" + "\n".join(schema_lines)
    )
    llm = LLMProviderFactory.create("openai")
    raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=user)])
    data = _parse_json_array(raw)

    valid_tables = {t.name for t in tables}
    valid_columns = {(t.name, c.name) for t in tables for c in t.columns}
    out: list[GlossaryEntry] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        table = str(item.get("table", "")).strip()
        if table not in valid_tables:
            continue
        column = item.get("column")
        column = str(column).strip() if column else None
        if column is not None and (table, column) not in valid_columns:
            continue
        entry_id = _glossary_id(table, column)
        if entry_id in seen:
            continue
        seen.add(entry_id)
        tags = item.get("tags") or []
        tags = [str(t).strip() for t in tags if str(t).strip()] if isinstance(tags, list) else []
        out.append(
            GlossaryEntry(
                id=entry_id,
                table=table,
                column=column,
                definition=str(item.get("definition", "")).strip(),
                tags=tags[:3],
                status="pending",
                source="llm",
            )
        )
    return out


def _parse_json_array(raw: str) -> list[Any]:
    text = raw.strip()
    if text.startswith("```"):
        # Strip ```json ... ``` fences.
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _generate_glossary_heuristic(tables: list[Any]) -> list[GlossaryEntry]:
    entries: list[GlossaryEntry] = []
    for table in tables:
        entries.append(
            GlossaryEntry(
                id=_glossary_id(table.name, None),
                table=table.name,
                column=None,
                definition=f"Table containing {len(table.columns)} columns.",
                status="pending",
                source="manual",
            )
        )
        for col in table.columns:
            tags = []
            if getattr(col, "is_primary_key", False):
                tags.append("identifier")
            entries.append(
                GlossaryEntry(
                    id=_glossary_id(table.name, col.name),
                    table=table.name,
                    column=col.name,
                    definition=f"{col.data_type} column on {table.name}.",
                    tags=tags,
                    status="pending",
                    source="manual",
                )
            )
    return entries


async def _generate_description(
    name: str,
    db_type: str,
    schema: SchemaMetadata,
    context: str,
) -> str:
    table_names = [t.name for t in schema.tables]
    try:
        system = (
            "You are a data catalog assistant. Write a concise 2-4 sentence "
            "description of a datasource's purpose and what kind of analytical "
            "questions it can answer. Plain prose, no markdown headings."
        )
        user = (
            f"Datasource name: {name}\n"
            f"Connector type: {db_type}\n"
            f"Tables: {', '.join(table_names) or 'unknown'}\n"
            f"Additional context: {context or 'none'}"
        )
        llm = LLMProviderFactory.create("openai")
        out = await llm.complete(system=system, messages=[LLMMessage(role="user", content=user)])
        if out.strip():
            return out.strip()
    except Exception:  # noqa: BLE001 - fall back to a heuristic summary
        pass
    return (
        f"{name} is a {db_type} datasource with {len(table_names)} table(s): "
        f"{', '.join(table_names[:10]) or 'no tables discovered'}. "
        "Use it to explore and query this data in natural language."
    )


async def _get_datasource(db: AsyncSession, tenant_id: uuid.UUID, datasource_id: uuid.UUID) -> DataSource:
    res = await db.execute(
        select(DataSource).where(DataSource.id == datasource_id, DataSource.tenant_id == tenant_id)
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="datasource not found")
    return ds


async def _ensure_conversation(
    db: AsyncSession,
    ctx: RequestContext,
    conversation_id: uuid.UUID,
    datasource_id: uuid.UUID,
    question: str,
) -> None:
    res = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == ctx.tenant_id,
            Conversation.user_id == ctx.user_id,
        )
    )
    conv = res.scalar_one_or_none()
    title = question[:80] + ("..." if len(question) > 80 else "")
    if conv is None:
        db.add(
            Conversation(
                id=conversation_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                title=title,
                datasource_id=datasource_id,
            )
        )
    else:
        conv.title = conv.title if conv.title != "New conversation" else title
        conv.datasource_id = datasource_id


DataSourceDetail.model_rebuild()
