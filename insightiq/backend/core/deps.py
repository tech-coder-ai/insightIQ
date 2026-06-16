from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config.settings import AppSettings, get_settings_resolver
from core.db import create_engine, create_sessionmaker


@lru_cache(maxsize=1)
def get_app_engine() -> AsyncEngine:
    settings = get_settings_resolver().resolve()
    return create_engine(settings)


@lru_cache(maxsize=1)
def get_app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(get_app_engine())


async def get_db() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_app_sessionmaker()
    async with sessionmaker() as session:
        yield session


def get_settings() -> AppSettings:
    return get_settings_resolver().resolve()
