"""Dialect-neutral SQLAlchemy column types shared by models and migrations."""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.types import Uuid

# Portable UUID (PostgreSQL UUID, SQLite CHAR(32)/hex storage via SQLAlchemy).
GUID = Uuid(as_uuid=True)

# Portable JSON document columns (JSONB on PostgreSQL when using .with_variant).
JSONType = JSON
