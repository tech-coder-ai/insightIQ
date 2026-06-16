from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.data.connectors.base import IDBConnector
from core.data.connectors.factory import ConnectorFactory
from core.data.session import create_datasource_engine

_SQLALCHEMY_TYPES = {"postgres"}


@asynccontextmanager
async def open_connector(db_type: str, connection: dict[str, Any]) -> AsyncIterator[IDBConnector]:
    if db_type in _SQLALCHEMY_TYPES:
        engine = create_datasource_engine(db_type, connection)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        async with sessionmaker() as session:
            yield ConnectorFactory.create(db_type, session=session)
        await engine.dispose()
        return

    connector = ConnectorFactory.create(db_type, connection=connection)
    try:
        yield connector
    finally:
        close = getattr(connector, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
