from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from config.settings import AppSettings


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


def create_engine(settings: AppSettings) -> AsyncEngine:
    url = settings.database.url
    kwargs: dict = {"pool_pre_ping": not is_sqlite_url(url)}
    if is_sqlite_url(url):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = NullPool
    return create_async_engine(url, **kwargs)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def create_migration_engine(settings: AppSettings) -> AsyncEngine:
    """One-shot engine for Alembic (always uses NullPool)."""
    url = settings.database.url
    kwargs: dict = {"poolclass": NullPool}
    if is_sqlite_url(url):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(url, **kwargs)


async def session_scope(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session
