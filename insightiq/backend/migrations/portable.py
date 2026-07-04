"""Dialect-neutral helpers for Alembic migrations (PostgreSQL + SQLite)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def _dialect_name() -> str:
    bind = op.get_bind()
    return bind.dialect.name if bind is not None else "postgresql"


def uuid_col(**kwargs: object) -> sa.Uuid:
    return sa.Uuid(as_uuid=True, **kwargs)


def json_col(**kwargs: object) -> sa.JSON:
    return sa.JSON(**kwargs)


def json_object_default() -> sa.TextClause:
    if _dialect_name() == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def json_array_default() -> sa.TextClause:
    if _dialect_name() == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def now_default() -> sa.TextClause:
    if _dialect_name() == "sqlite":
        return sa.text("(datetime('now'))")
    return sa.text("now()")


def bool_default(value: bool) -> sa.TextClause:
    if _dialect_name() == "sqlite":
        return sa.text("1" if value else "0")
    return sa.text("true" if value else "false")


def user_role_column(**kwargs: object) -> sa.Enum:
    return sa.Enum(
        "viewer",
        "editor",
        "admin",
        "super-admin",
        name="role",
        native_enum=False,
        **kwargs,
    )


def drop_pg_enum(name: str) -> None:
    if _dialect_name() == "postgresql":
        op.execute(f"DROP TYPE {name}")
