from __future__ import annotations

import csv
import io
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.chat_history import load_llm_history
from core.data.connection import mask_connection, merge_connection
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
    connection: dict[str, Any] = Field(default_factory=dict)
    schema_metadata: SchemaMetadata
    selected_scope: SelectedScope
    relationships: list[Relationship]
    glossary: list[GlossaryEntry]


class UpdateDataSourceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    connection: dict[str, Any] | None = None


class TestConnectionRequest(BaseModel):
    connection: dict[str, Any] | None = None


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
    suggested_rephrase: str = ""


@dataclass
class SqlResolution:
    sql: str | None = None
    clarification: str | None = None
    proposal: SqlProposal | None = None


@dataclass
class SqlJudgement:
    """Confidence score + verdict for a candidate SQL query before it runs."""

    sql: str | None = None
    confidence: float = 0.0
    interpretation: str = ""
    clarifying_question: str | None = None
    suggested_rephrase: str | None = None


# Confidence thresholds driving the run / confirm / clarify decision:
# >= _CONFIDENCE_AUTO_RUN  -> execute immediately, no confirmation needed.
# [_CONFIDENCE_CLARIFY, _CONFIDENCE_AUTO_RUN) -> show the proposed SQL and ask to confirm.
# < _CONFIDENCE_CLARIFY -> too unsure to propose SQL at all; ask a clarifying question.
_CONFIDENCE_AUTO_RUN = 0.75
_CONFIDENCE_CLARIFY = 0.4


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
        connection=mask_connection(ds.connection_config_json),
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
    if req.connection is not None:
        ds.connection_config_json = await _validate_and_merge_connection(ds, req.connection)
    await db.commit()
    await db.refresh(ds)
    return _to_response(ds)


@router.post("/sources/{datasource_id}/test")
async def test_source(
    datasource_id: uuid.UUID,
    req: TestConnectionRequest | None = None,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    connection = ds.connection_config_json or {}
    if req and req.connection is not None:
        if ds.db_type == "duckdb_files":
            raise HTTPException(
                status_code=400,
                detail="file-based datasources use stored files; connection cannot be tested with draft settings",
            )
        connection = merge_connection(connection, req.connection)
    try:
        async with open_connector(ds.db_type, connection) as connector:
            ok = await connector.test_connection()
    except HTTPException:
        raise
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

    pending: dict[str, str] | None = None
    if req.conversation_id:
        pending = await _get_pending_proposal(db, ctx, req.conversation_id)

    intent = await _classify_message_intent(req.question, has_pending_proposal=bool(pending))

    if intent == "smalltalk":
        message = _smalltalk_reply(req.question) or _SMALLTALK_REPLIES["acknowledge"]
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
        return AskResponse(conversation_id=conversation_id, sql="", response=response)

    if intent == "reject" and pending and req.conversation_id:
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
        if intent == "confirm" and pending and req.conversation_id:
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

        direct_answer = await _maybe_answer_from_context(
            question=req.question,
            history=prior_history,
            schema=schema,
        )
        if direct_answer:
            response = format_explanation(output=direct_answer, title=req.question)
            await _persist_ask_messages(
                db,
                ctx=ctx,
                conversation_id=conversation_id,
                datasource_id=ds.id,
                question=req.question,
                sql="",
                response=response,
            )
            return AskResponse(conversation_id=conversation_id, sql="", response=response)

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
                history=prior_history,
            )

        if resolution.clarification:
            proposal = await _build_sql_proposal(
                dialect=ds.dialect,
                schema=schema,
                question=req.question,
                connector=connector,
                context=resolution.clarification,
                history=prior_history,
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
                    history=prior_history,
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
    return datetime.now(UTC).isoformat()


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
        "- For superlative questions ('most', 'top', 'highest', 'best', 'least', 'lowest', 'worst'), "
        "compute the ranking metric explicitly — GROUP BY the entity, aggregate (COUNT/SUM/AVG) the metric "
        "across any related tables needed (e.g. 'most rented film' requires counting rental rows per film, "
        "typically joining film -> inventory -> rental), then ORDER BY the aggregate DESC/ASC and LIMIT "
        "accordingly. Never answer a superlative question with a plain SELECT * from an unrelated table.\n"
        "- The conversation history (if any) includes prior questions, the SQL that ran, and the actual "
        "result rows/values returned. When the user refers back to an entity from a previous turn "
        "('this film', 'that customer', 'it', 'those orders'), resolve it to the SPECIFIC value(s) already "
        "shown in the prior result (by exact name/id) and filter directly on it (e.g. WHERE title = "
        "'<exact title from history>') — do NOT recompute a ranking or pick a new/different entity.\n"
        f"{chart_date_sql_rules(dialect, question)}\n\n"
        "Schema:\n" + ("\n".join(table_lines) or "- table: unknown") + "\n\n"
        "Relationships:\n" + ("\n".join(rel_lines) or "- none") + "\n\n"
        "Glossary:\n" + ("\n".join(glossary_lines) or "- none")
    )


async def _maybe_answer_from_context(
    *,
    question: str,
    history: list[LLMMessage],
    schema: SchemaMetadata,
) -> str | None:
    """Answer a follow-up directly from the conversation so far when no new query is needed.

    Not every message needs a fresh SQL round-trip — e.g. "what did you mean by that", "explain
    the previous result", or "what tables can I ask about" can be answered from history/schema
    alone. Returns None (falls through to the SQL pipeline) whenever there's no history, no LLM
    available, or the question needs data that hasn't already been returned.
    """
    if not history:
        return None
    table_names = ", ".join(t.name for t in schema.tables[:30]) or "none"
    system = (
        "You decide whether a user's follow-up message can be answered directly from the "
        "conversation history below (which includes prior questions, the SQL that ran, and the "
        "actual results returned), or whether it requires running a NEW SQL query.\n"
        "Answer directly ONLY when the user is asking you to repeat, summarize, explain, interpret, "
        "or compare something already present in a previous result, or is asking a meta question "
        "about what data/tables are available. Do NOT answer directly if they want different rows, "
        "columns, filters, entities, or any value not already shown above — in that case a new query "
        "is required, even if it references something from before (e.g. 'the cast of that film' still "
        "needs a new query, but should reuse the specific film name/id already established above).\n"
        f"Known tables: {table_names}\n"
        'Respond ONLY with JSON: {"answer": "<direct answer using only what is already in history>"} '
        'if you can answer directly, or {"answer": null} if a new query is needed.'
    )
    messages = [*history, LLMMessage(role="user", content=question)]
    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=messages)
        payload = _parse_json_object(raw)
        if payload:
            answer = payload.get("answer")
            if answer:
                return str(answer).strip()
    except Exception:  # noqa: BLE001 - no LLM available, always fall back to the SQL pipeline
        pass
    return None


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


# Pure conversational messages that never need a SQL round-trip. Kept disjoint from
# _AFFIRMATIVE/_NEGATIVE (e.g. no "ok"/"sure"/"great") so confirming or rejecting a
# pending SQL proposal is never accidentally swallowed as small talk.
_SMALLTALK_PATTERNS: dict[str, re.Pattern[str]] = {
    "thanks": re.compile(
        r"^(?:thanks|thank you|thank u|thx|ty|many thanks|thanks a lot|thanks so much|"
        r"thanks a bunch|much appreciated|appreciate it|appreciated|cheers)[!.]*$",
        re.IGNORECASE,
    ),
    "greeting": re.compile(
        r"^(?:hi|hello|hey|hiya|yo|good morning|good afternoon|good evening)[!.]*$",
        re.IGNORECASE,
    ),
    "farewell": re.compile(
        r"^(?:bye|goodbye|bye bye|see ya|see you|later|take care|talk soon)[!.]*$",
        re.IGNORECASE,
    ),
    "acknowledge": re.compile(
        r"^(?:cool|nice|great|awesome|perfect|sweet|got it|nice one|well done|nicely done|"
        r"lol|haha|no worries|np|you're welcome|youre welcome)[!.]*$",
        re.IGNORECASE,
    ),
}
_SMALLTALK_REPLIES: dict[str, str] = {
    "thanks": "You're welcome! Let me know if you'd like to dig into anything else.",
    "greeting": "Hi! Ask me anything about your data — I'll turn it into a query and show you the results.",
    "farewell": "Goodbye! Come back anytime you have more questions about your data.",
    "acknowledge": "Glad that helped! Let me know if there's anything else you'd like to explore.",
}


def _smalltalk_reply(question: str) -> str | None:
    """Return a canned reply for pure chit-chat (thanks/greetings/etc.), or None otherwise.

    Used both as the text source for a "smalltalk" classification and as the offline
    fallback classifier itself when no LLM is configured.
    """
    text = question.strip()
    for kind, pattern in _SMALLTALK_PATTERNS.items():
        if pattern.match(text):
            return _SMALLTALK_REPLIES[kind]
    return None


_MESSAGE_INTENTS = {"confirm", "reject", "smalltalk", "data_question"}


async def _classify_message_intent(question: str, *, has_pending_proposal: bool) -> str:
    """Classify what the user's message wants: confirm/reject a pending query, pure
    chit-chat, or a real data question.

    A lightweight LLM call handles this by default — it generalizes far better than fixed
    phrase lists (typos, other phrasings, "yeah that's the one", "nah try again", etc.).
    The regex lists (_AFFIRMATIVE/_NEGATIVE/_SMALLTALK_PATTERNS) only kick in as a fallback
    when no LLM is configured, so the app still behaves sensibly offline/in dev — the same
    "LLM primary, heuristic fallback" pattern used for SQL generation elsewhere in this file.
    """
    system = (
        "Classify the user's latest chat message into exactly one intent:\n"
        '- "confirm": agreeing to run a SQL query that was just proposed to them '
        "(e.g. 'yes', 'go ahead', 'looks right', 'yeah that's the one').\n"
        '- "reject": declining a just-proposed query because it is wrong '
        "(e.g. 'no', 'that's not it', 'try again').\n"
        '- "smalltalk": pure conversational filler with no data request at all — greetings, '
        "thanks, farewells, or acknowledgements ('thanks!', 'hi', 'bye', 'cool, nice one').\n"
        '- "data_question": anything asking about, requesting, or following up on actual data. '
        "Use this whenever in doubt.\n"
        f"There {'IS' if has_pending_proposal else 'is NOT'} a SQL query currently awaiting the "
        "user's confirmation, so only classify as confirm/reject when that's true.\n"
        'Respond ONLY with JSON: {"intent": "confirm" | "reject" | "smalltalk" | "data_question"}'
    )
    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=[LLMMessage(role="user", content=question)])
        payload = _parse_json_object(raw)
        intent = str((payload or {}).get("intent", "")).strip().lower()
        if intent in _MESSAGE_INTENTS:
            return intent
    except Exception:  # noqa: BLE001 - no LLM available, fall back to fast regex heuristics
        pass

    if _is_affirmative(question):
        return "confirm"
    if _is_negative(question):
        return "reject"
    if _smalltalk_reply(question) is not None:
        return "smalltalk"
    return "data_question"


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
    message = (
        f"I think you're asking for: {proposal.interpretation}\n\n"
        "Does that look right? Reply yes to run the query, or no to rephrase."
    )
    if proposal.suggested_rephrase:
        message += f'\n\nTip: for a more precise answer, try asking: "{proposal.suggested_rephrase}"'
    return message


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
    history: list[LLMMessage] | None = None,
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
            history=history,
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
    if proposal.suggested_rephrase:
        response.data["suggested_rephrase"] = proposal.suggested_rephrase

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
    history: list[LLMMessage] | None = None,
) -> SqlProposal | None:
    schema_lines = []
    for table in schema.tables:
        cols = ", ".join(f"{c.name} ({c.data_type})" for c in table.columns)
        schema_lines.append(f"{table.name}: {cols}")

    system = (
        f"You are a {dialect} analyst. Given a user question and schema metadata, infer the most likely intent "
        "and write ONE read-only SELECT using ONLY listed tables and columns. "
        "Map business terms to the closest schema columns (e.g. cost/revenue → amount). "
        "For superlative questions ('most', 'top', 'highest', 'least'), aggregate and JOIN across related "
        "tables as needed, then ORDER BY the aggregate and LIMIT — never fall back to an unrelated SELECT *. "
        "The user's prior conversation turns (if any) are included as message history before the final "
        "question — use them to resolve references like 'this film' / 'that customer' to concrete values "
        "(e.g. from a 'Result: ...' line in a prior assistant turn), and prefer a fresh, well-scoped query "
        "over repeating an earlier one when the current question asks for different columns or detail.\n"
        f"{chart_date_sql_rules(dialect, question)} "
        "Respond ONLY with JSON (no markdown): "
        '{"interpretation": "plain English summary of what you will query", "sql": "SELECT ...", '
        '"suggested_rephrase": "an example of a more precise way to ask this" or null}'
    )
    user = (
        f"User question: {question}\n"
        f"Schema:\n" + "\n".join(schema_lines) + "\n"
        + (f"Context: {context}\n" if context else "")
        + (f"Draft SQL (fix if needed): {draft_sql}\n" if draft_sql else "")
    )
    messages = [*(history or []), LLMMessage(role="user", content=user)]

    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=messages)
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
    rephrase = payload.get("suggested_rephrase")
    rephrase = str(rephrase).strip() if rephrase else ""
    if interpretation and sql:
        return SqlProposal(
            interpretation=interpretation,
            sql=sql,
            original_question=original_question,
            suggested_rephrase=rephrase,
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
    """Generate SQL, score confidence, and either run it, propose it, or ask the user."""
    messages = list(prior_messages or [])
    messages.append(LLMMessage(role="user", content=question))
    last_error = ""
    last_sql = ""

    for attempt in range(max_retries):
        raw, used_llm = await _complete_sql_llm_raw(system_prompt, messages)
        sql, clarify = _parse_llm_sql_response(raw)
        if clarify:
            proposal = await _build_sql_proposal(
                dialect=dialect,
                schema=schema,
                question=question,
                connector=connector,
                context=clarify,
                draft_sql=last_sql,
                history=prior_messages,
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

        judged = await _judge_sql(
            dialect=dialect,
            schema=schema,
            question=question,
            sql=sql,
            llm_generated=used_llm,
            history=prior_messages,
        )
        if judged.sql and judged.sql != sql:
            fix_guard = check_readonly_select(judged.sql)
            fix_schema_check = validate_sql_against_schema(judged.sql, schema)
            if fix_guard.ok and fix_schema_check.ok:
                sql = judged.sql

        if judged.confidence < _CONFIDENCE_CLARIFY:
            clar_text = judged.clarifying_question or (
                f"I'm not confident I understood \"{question}\" correctly against the current schema."
            )
            if judged.suggested_rephrase:
                clar_text += f'\n\nTip: try asking, for example: "{judged.suggested_rephrase}"'
            return SqlResolution(clarification=clar_text)

        if judged.confidence < _CONFIDENCE_AUTO_RUN:
            return SqlResolution(
                proposal=SqlProposal(
                    interpretation=judged.interpretation or f"Run a query to answer: {question}",
                    sql=sql,
                    original_question=question,
                    suggested_rephrase=judged.suggested_rephrase or "",
                )
            )

        # High confidence: validate against the live database and execute directly.
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
        history=prior_messages,
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


async def _judge_sql(
    *,
    dialect: str,
    schema: SchemaMetadata,
    question: str,
    sql: str,
    llm_generated: bool,
    history: list[LLMMessage] | None = None,
) -> SqlJudgement:
    """Score confidence that ``sql`` correctly answers ``question`` before it runs.

    When the SQL came from the heuristic (no-LLM) fallback, confidence is always low
    since that path cannot reliably reason about joins/aggregations — the caller
    should ask the user to confirm or clarify rather than execute it.
    """
    if not llm_generated:
        return _heuristic_judgement(question, schema, sql)

    schema_lines = []
    for table in schema.tables:
        cols = ", ".join(f"{c.name} ({c.data_type})" for c in table.columns)
        schema_lines.append(f"{table.name}: {cols}")

    system = (
        f"You are a careful {dialect} data analyst reviewing a generated SQL query before it runs. "
        "Score how confident you are that this query correctly answers the user's question using ONLY the "
        "schema below — consider whether it uses the right tables/joins/aggregation for the intent (e.g. "
        "'most rented film' needs a COUNT of rentals per film via inventory, ORDER BY DESC, LIMIT), and "
        "whether it matches the requested grain and filters. If the question references something from "
        "earlier in the conversation (e.g. 'this film', 'that customer'), check the prior turns (including "
        "any 'Result: ...' lines) to confirm the query is scoped to the SAME specific entity — lower "
        "confidence if it isn't.\n"
        "Respond ONLY with JSON (no markdown): "
        '{"confidence": 0.0-1.0, "sql": "the query, corrected if needed", '
        '"interpretation": "plain-English summary of what this query returns", '
        '"clarifying_question": "question to ask the user" or null, '
        '"suggested_rephrase": "an example of how the user could phrase this more precisely" or null}\n'
        "Use confidence below 0.4 with a clarifying_question when the question is ambiguous or the query is "
        "unlikely to be correct. Use confidence 0.4-0.75 when the query is a reasonable guess that should be "
        "confirmed. Use confidence above 0.75 only when you are confident the query is correct as-is. "
        "Always set suggested_rephrase when a more specific phrasing would meaningfully improve accuracy."
    )
    user = (
        f"User question: {question}\n\n"
        f"Schema:\n" + "\n".join(schema_lines) + "\n\n"
        f"Generated SQL:\n{sql}"
    )
    messages = [*(history or []), LLMMessage(role="user", content=user)]

    try:
        llm = LLMProviderFactory.create("openai")
        raw = await llm.complete(system=system, messages=messages)
        parsed = _parse_judgement_json(raw)
        if parsed is not None:
            return parsed
    except Exception:  # noqa: BLE001 - trust the generation if judging is unavailable
        pass

    return SqlJudgement(sql=sql, confidence=1.0, interpretation=f"Run a query to answer: {question}")


def _heuristic_judgement(question: str, schema: SchemaMetadata, sql: str) -> SqlJudgement:
    tables = ", ".join(t.name for t in schema.tables[:8]) or "none"
    clarifying = (
        "I don't have an LLM connected right now, so I can only do simple keyword matching and I'm not "
        f'confident that answers "{question}" correctly. '
        f"Available tables: {tables}. Could you name the exact table, metric, and any filters you want?"
    )
    return SqlJudgement(
        sql=sql,
        confidence=0.15,
        interpretation=f"Best-effort keyword match against: {tables}",
        clarifying_question=clarifying,
        suggested_rephrase=_example_rephrase(schema),
    )


def _example_rephrase(schema: SchemaMetadata) -> str | None:
    for table in schema.tables:
        numeric = next(
            (
                c.name
                for c in table.columns
                if any(hint in c.data_type.lower() for hint in ("int", "numeric", "decimal", "float", "double"))
                and not c.is_primary_key
            ),
            None,
        )
        if numeric:
            return f"Show total {numeric} by {table.name}"
    if schema.tables:
        return f"Show the top 10 rows from {schema.tables[0].name}"
    return None


def _parse_judgement_json(raw: str) -> SqlJudgement | None:
    payload = _parse_json_object(raw)
    if payload is None:
        return None
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    sql = _extract_sql(str(payload.get("sql", "") or "")) or None
    interpretation = str(payload.get("interpretation", "") or "").strip()
    clarifying_question = payload.get("clarifying_question")
    clarifying_question = str(clarifying_question).strip() if clarifying_question else None
    suggested_rephrase = payload.get("suggested_rephrase")
    suggested_rephrase = str(suggested_rephrase).strip() if suggested_rephrase else None

    return SqlJudgement(
        sql=sql,
        confidence=confidence,
        interpretation=interpretation,
        clarifying_question=clarifying_question or None,
        suggested_rephrase=suggested_rephrase or None,
    )


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


async def _complete_sql_llm_raw(system_prompt: str, messages: list[LLMMessage]) -> tuple[str, bool]:
    """Call OpenAI for NL→SQL; fall back to heuristic when LLM is unavailable.

    Returns ``(text, used_llm)`` so callers can treat heuristic output as low-confidence.
    """
    try:
        llm = LLMProviderFactory.create("openai")
        return await llm.complete(system=system_prompt, messages=messages), True
    except Exception:  # noqa: BLE001
        pass
    llm = LLMProviderFactory.create("heuristic")
    return await llm.complete(system=system_prompt, messages=messages), False


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
    raw, _used_llm = await _complete_sql_llm_raw(system_prompt, messages)
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


async def _validate_and_merge_connection(ds: DataSource, incoming: dict[str, Any]) -> dict[str, Any]:
    if ds.db_type == "duckdb_files":
        raise HTTPException(
            status_code=400,
            detail="file-based datasources cannot change connection settings; upload a new datasource instead",
        )
    merged = merge_connection(ds.connection_config_json or {}, incoming)
    try:
        async with open_connector(ds.db_type, merged) as connector:
            if not await connector.test_connection():
                raise HTTPException(status_code=400, detail="connection failed")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"connection failed: {exc}") from exc
    return merged


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
