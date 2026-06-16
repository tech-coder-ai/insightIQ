from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_indexed: bool = False


class IndexMeta(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    unique: bool = False


class TableMeta(BaseModel):
    name: str
    columns: list[ColumnMeta] = Field(default_factory=list)
    indexes: list[IndexMeta] = Field(default_factory=list)


class RelationshipMeta(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    source: str = "manual"  # "introspected" | "manual"


class SchemaMetadata(BaseModel):
    tables: list[TableMeta] = Field(default_factory=list)
    relationships: list[RelationshipMeta] = Field(default_factory=list)
