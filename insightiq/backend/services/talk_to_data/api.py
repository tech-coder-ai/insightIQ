from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

SUPPORTED_DB_TYPES = {"postgres", "s3_object_store", "duckdb_files"}
DIALECT_BY_DB_TYPE = {
    "postgres": "postgres",
    "s3_object_store": "duckdb",
    "duckdb_files": "duckdb",
}


class RegisterDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    db_type: str
    connection: dict[str, Any]


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str
    dialect: str


class Relationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class GlossaryTerm(BaseModel):
    term: str
    definition: str
    table: str | None = None
    column: str | None = None


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
        connection_config_json=req.connection,
        schema_snapshot_json=schema.model_dump(),
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse(id=ds.id, name=ds.name, db_type=ds.db_type, dialect=ds.dialect)


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_sources(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DataSourceResponse]:
    res = await db.execute(select(DataSource).where(DataSource.tenant_id == ctx.tenant_id))
    return [
        DataSourceResponse(id=ds.id, name=ds.name, db_type=ds.db_type, dialect=ds.dialect)
        for ds in res.scalars().all()
    ]


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
    return [Relationship.model_validate(r) for r in ds.relationships_json]


@router.post("/sources/{datasource_id}/glossary/generate", response_model=list[GlossaryTerm])
async def generate_glossary(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_role(Role.editor)),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryTerm]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    schema = SchemaMetadata.model_validate(ds.schema_snapshot_json or {"tables": []})
    terms = _generate_glossary_from_schema(schema)
    ds.glossary_json = [t.model_dump() for t in terms]
    await db.commit()
    return terms


@router.get("/sources/{datasource_id}/glossary", response_model=list[GlossaryTerm])
async def get_glossary(
    datasource_id: uuid.UUID,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[GlossaryTerm]:
    ds = await _get_datasource(db, ctx.tenant_id, datasource_id)
    return [GlossaryTerm.model_validate(t) for t in ds.glossary_json]


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
    system_prompt = _build_sql_system_prompt(ds.dialect, schema, ds.glossary_json)
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


def _build_sql_system_prompt(dialect: str, schema: SchemaMetadata, glossary: list) -> str:
    table_lines = []
    for table in schema.tables:
        cols = ", ".join(c.name for c in table.columns)
        table_lines.append(f"- table: {table.name} ({cols})")
    glossary_lines = [
        f"- {g.get('term')}: {g.get('definition')}" for g in glossary[:20]
    ]
    return (
        f"You generate read-only {dialect} SQL.\n"
        "Only output a single SELECT statement. No markdown.\n"
        f"Available tables:\n" + ("\n".join(table_lines) or "- table: unknown") + "\n"
        f"Glossary:\n" + ("\n".join(glossary_lines) or "- none")
    )


def _generate_glossary_from_schema(schema: SchemaMetadata) -> list[GlossaryTerm]:
    terms: list[GlossaryTerm] = []
    for table in schema.tables:
        terms.append(
            GlossaryTerm(
                term=table.name,
                definition=f"Table containing {len(table.columns)} columns.",
                table=table.name,
            )
        )
        for col in table.columns:
            terms.append(
                GlossaryTerm(
                    term=col.name,
                    definition=f"{col.data_type} column on {table.name}.",
                    table=table.name,
                    column=col.name,
                )
            )
    return terms
