from __future__ import annotations

from enum import StrEnum


class DBType(StrEnum):
    postgres = "postgres"
    s3_object_store = "s3_object_store"
    duckdb_files = "duckdb_files"

