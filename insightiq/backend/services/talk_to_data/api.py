from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.connectors.factory import ConnectorFactory
from core.data.session import create_datasource_engine
from core.deps import get_db
from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory
from core.models import ChatMessage, DataSource
from core.request_context import RequestContext, require_auth, require_role
from core.response.formatter import format_data_table
from core.response.types import ResponsePayload
from core.types import Role


router = APIRouter(prefix="/talk-to-data", tags=["talk-to-data"])


class PostgresConnection(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str
    user: str
    password: str = Field(repr=False)


class RegisterDataSourceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    db_type: str = Field(pattern=r"^postgres$")
    connection: PostgresConnection


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    db_type: str


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
    connection = req.connection.model_dump()
    await _test_datasource(req.db_type, connection)

    ds = DataSource(
        tenant_id=ctx.tenant_id,
        name=req.name,
        db_type=req.db_type,
        connection_config_json=connection,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return DataSourceResponse(id=ds.id, name=ds.name, db_type=ds.db_type)


@router.get("/sources", response_model=list[DataSourceResponse])
async def list_sources(
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> list[DataSourceResponse]:
    res = await db.execute(select(DataSource).where(DataSource.tenant_id == ctx.tenant_id))
    return [
        DataSourceResponse(id=ds.id, name=ds.name, db_type=ds.db_type) for ds in res.scalars().all()
    ]


@router.post("/ask", response_model=AskResponse)
async def ask(
    req: AskRequest,
    ctx: RequestContext = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    ds = await _get_datasource(db, ctx.tenant_id, req.datasource_id)
    conversation_id = req.conversation_id or uuid.uuid4()

    tables = await _list_tables(ds.db_type, ds.connection_config_json)
    system_prompt = _build_sql_system_prompt(ds.db_type, tables)
    llm = LLMProviderFactory.create("heuristic")
    sql = (await llm.complete(system=system_prompt, messages=[LLMMessage(role="user", content=req.question)])).strip()
    sql = sql.rstrip(";")

    result = await _execute_with_validation(ds.db_type, ds.connection_config_json, sql)
    response = format_data_table(result, title=req.question)

    user_msg = ChatMessage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation_id=conversation_id,
        role="user",
        content=req.question,
        metadata_json={"datasource_id": str(ds.id)},
    )
    assistant_msg = ChatMessage(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        conversation_id=conversation_id,
        role="assistant",
        content=sql,
        metadata_json={"response": response.model_dump()},
    )
    db.add(user_msg)
    db.add(assistant_msg)
    await db.commit()

    return AskResponse(conversation_id=conversation_id, sql=sql, response=response)


async def _get_datasource(db: AsyncSession, tenant_id: uuid.UUID, datasource_id: uuid.UUID) -> DataSource:
    res = await db.execute(
        select(DataSource).where(DataSource.id == datasource_id, DataSource.tenant_id == tenant_id)
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="datasource not found")
    return ds


async def _test_datasource(db_type: str, connection: dict) -> None:
    engine = create_datasource_engine(db_type, connection)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            connector = ConnectorFactory.create(db_type, session=session)
            ok = await connector.test_connection()
            if not ok:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="connection failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    finally:
        await engine.dispose()


async def _list_tables(db_type: str, connection: dict) -> list[str]:
    if db_type != "postgres":
        return []
    engine = create_datasource_engine(db_type, connection)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            res = await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
            )
            return [row[0] for row in res.fetchall()]
    finally:
        await engine.dispose()


async def _execute_with_validation(db_type: str, connection: dict, sql: str):
    engine = create_datasource_engine(db_type, connection)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            connector = ConnectorFactory.create(db_type, session=session)
            validation = await connector.validate_sql(sql)
            if not validation.ok:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=validation.error or "invalid SQL",
                )
            return await connector.execute_query(sql)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    finally:
        await engine.dispose()


def _build_sql_system_prompt(db_type: str, tables: list[str]) -> str:
    table_lines = "\n".join(f"- table: {t}" for t in tables) or "- table: unknown"
    return (
        f"You generate read-only {db_type} SQL.\n"
        "Only output a single SELECT statement. No markdown.\n"
        f"Available tables:\n{table_lines}"
    )
