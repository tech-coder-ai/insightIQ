from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from config.settings import AppSettings
from core.db import create_engine, create_migration_engine, is_sqlite_url
from core.models import Base, Tenant


@pytest.mark.asyncio
async def test_sqlite_metadata_create_all() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        tables = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
    assert "tenants" in tables
    assert "users" in tables
    await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_insert_and_read_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with sessionmaker() as session:
        session.add(Tenant(name="sqlite-tenant"))
        await session.commit()

    async with sessionmaker() as session:
        res = await session.execute(text("SELECT name FROM tenants"))
        assert res.scalar_one() == "sqlite-tenant"

    await engine.dispose()


def test_is_sqlite_url() -> None:
    assert is_sqlite_url("sqlite+aiosqlite:///./dev.db")
    assert not is_sqlite_url("postgresql+asyncpg://localhost/db")


def test_create_engine_from_settings_sqlite() -> None:
    settings = AppSettings(database={"url": "sqlite+aiosqlite:///:memory:"})
    engine = create_engine(settings)
    assert engine.url.get_backend_name() == "sqlite"


def test_create_migration_engine_sqlite() -> None:
    settings = AppSettings(database={"url": "sqlite+aiosqlite:///:memory:"})
    engine = create_migration_engine(settings)
    assert engine.url.get_backend_name() == "sqlite"
