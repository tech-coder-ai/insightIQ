from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_postgres_url(connection: dict[str, Any]) -> str:
    user = quote_plus(str(connection["user"]))
    password = quote_plus(str(connection["password"]))
    host = connection.get("host", "localhost")
    port = connection.get("port", 5432)
    database = connection["database"]
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def create_datasource_engine(db_type: str, connection: dict[str, Any]) -> AsyncEngine:
    if db_type == "postgres":
        return create_async_engine(build_postgres_url(connection), pool_pre_ping=True)
    raise ValueError(f"unsupported db_type: {db_type}")


async def datasource_session(
    db_type: str, connection: dict[str, Any]
) -> AsyncIterator[AsyncSession]:
    engine = create_datasource_engine(db_type, connection)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()
