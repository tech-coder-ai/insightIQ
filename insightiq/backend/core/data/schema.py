from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    name: str
    data_type: str
    nullable: bool = True


class TableMeta(BaseModel):
    name: str
    columns: list[ColumnMeta] = Field(default_factory=list)


class SchemaMetadata(BaseModel):
    tables: list[TableMeta] = Field(default_factory=list)
