from __future__ import annotations

import csv
import io
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import get_settings_resolver
from core.data.runner import open_connector
from core.data.schema import SchemaMetadata
from core.deps import get_db
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.models import ChatMessage, Conversation, DataSource
from core.request_context import RequestContext, require_auth, require_role
from core.response.classifier import classify_and_format
from core.response.types import ResponsePayload
from core.types import Role

router = APIRouter(prefix="/talk-to-data", tags=["talk-to-data"])

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


class RegisterDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    db_type: str
    connection: dict[str, Any]
    description: str = ""


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str
    dialect: str
    description: str = ""
    metadata_status: str = "draft"


class DataSourceDetail(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str
    dialect: str
    description: str = ""
    metadata_status: str = "draft"
    schema_metadata: SchemaMetadata
    relationships: list["Relationship"]
    glossary: list["GlossaryEntry"]


class UpdateDataSourceRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


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


class AskResponse(BaseModel):
    conversation_id: uuid.UUID
    sql: str
    response: ResponsePayload


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

    ds = DataSource(
        tenant_id=ctx.tenant_id,
        name=req.name,
        db_type=req.db_type,
        dialect=DIALECT_BY_DB_TYPE[req.db_type],
        description=req.description,
        connection_config_json=req.connection,
        schema_snapshot_json=schema.model_dump(),
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


ALLOWED_UPLOAD_SUFFIXES = {".csv", ".parquet", ".pq"}


@router.post("/sources/upload", response_model=DataSourceResponse)
async def upload_file_source(
    name: str = Form(...),
    table_name: str = Form("data"),
    description: str = Form(""),
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

    ds = DataSource(
        id=source_id,
        tenant_id=ctx.tenant_id,
        name=name,
        db_type="duckdb_files",
        dialect=DIALECT_BY_DB_TYPE["duckdb_files"],
        description=description,
        connection_config_json=connection,
        schema_snapshot_json=schema.model_dump(),
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
    schema = SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})
    return DataSourceDetail(
        id=ds.id,
        name=ds.name,
        db_type=ds.db_type,
        dialect=ds.dialect,
        description=ds.description or "",
        metadata_status=ds.metadata_status or "draft",
        schema_metadata=schema,
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
    schema = SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})
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

    schema = SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})
    relationships = [Relationship.model_validate(r) for r in (ds.relationships_json or [])]
    glossary = [e for e in _load_glossary(ds) if e.status == "approved"]
    system_prompt = _build_sql_system_prompt(ds.dialect, schema, relationships, glossary)
    llm = LLMProviderFactory.create("heuristic")
    sql = (
        await llm.complete(system=system_prompt, messages=[LLMMessage(role="user", content=req.question)])
    ).strip().rstrip(";")

    async with open_connector(ds.db_type, ds.connection_config_json) as connector:
        validation = await connector.validate_sql(sql)
        if not validation.ok:
            raise HTTPException(status_code=400, detail=validation.error or "invalid SQL")
        result = await connector.execute_query(sql)

    response = classify_and_format(result, question=req.question)

    db.add(
        ChatMessage(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation_id=conversation_id,
            role="user",
            content=req.question,
            metadata_json={"datasource_id": str(ds.id)},
        )
    )
    db.add(
        ChatMessage(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=sql,
            metadata_json={"response": response.model_dump()},
        )
    )
    await db.commit()
    return AskResponse(conversation_id=conversation_id, sql=sql, response=response)


def _sanitize_identifier(value: str) -> str:
    """Reduce a user-supplied table name to a safe SQL identifier."""
    cleaned = "".join(c if c.isalnum() or c == "_" else "_" for c in value.strip().lower())
    cleaned = cleaned.strip("_")
    if cleaned and cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:63]


def _to_response(ds: DataSource) -> DataSourceResponse:
    return DataSourceResponse(
        id=ds.id,
        name=ds.name,
        db_type=ds.db_type,
        dialect=ds.dialect,
        description=ds.description or "",
        metadata_status=ds.metadata_status or "draft",
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
) -> str:
    table_lines = []
    for table in schema.tables:
        cols = ", ".join(c.name for c in table.columns)
        table_lines.append(f"- table: {table.name} ({cols})")
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
        f"You generate read-only {dialect} SQL.\n"
        "Only output a single SELECT statement. No markdown.\n"
        "Available tables:\n" + ("\n".join(table_lines) or "- table: unknown") + "\n"
        "Relationships:\n" + ("\n".join(rel_lines) or "- none") + "\n"
        "Glossary:\n" + ("\n".join(glossary_lines) or "- none")
    )


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
