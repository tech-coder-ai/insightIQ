"""document versioning, original storage metadata, chunk highlight regions

Revision ID: 0012_document_versioning
Revises: 0011_chunk_parent_offsets
Create Date: 2026-07-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_document_versioning"
down_revision = "0011_chunk_parent_offsets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("registry_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("version_number", sa.Integer(), server_default="1", nullable=False))
    op.add_column("documents", sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("documents", sa.Column("storage_path", sa.String(length=1024), nullable=True))
    op.add_column("documents", sa.Column("mime_type", sa.String(length=128), nullable=True))
    op.add_column("documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("status", sa.String(length=32), server_default="active", nullable=False))
    op.add_column("documents", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("documents", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("ingested_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("documents", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE documents SET registry_id = id WHERE registry_id IS NULL")

    op.alter_column("documents", "registry_id", nullable=False)
    op.create_index("ix_documents_registry_id", "documents", ["registry_id"])
    op.create_index("ix_documents_collection_current", "documents", ["collection_id", "is_current"])

    op.add_column("document_chunks", sa.Column("bbox_json", postgresql.JSONB(), nullable=True))
    op.add_column("document_chunks", sa.Column("highlight_regions", postgresql.JSONB(), nullable=True))
    op.add_column("document_chunks", sa.Column("version_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "version_number")
    op.drop_column("document_chunks", "highlight_regions")
    op.drop_column("document_chunks", "bbox_json")
    op.drop_index("ix_documents_collection_current", table_name="documents")
    op.drop_index("ix_documents_registry_id", table_name="documents")
    op.drop_column("documents", "superseded_at")
    op.drop_column("documents", "ingested_by")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "file_size_bytes")
    op.drop_column("documents", "status")
    op.drop_column("documents", "content_hash")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "storage_path")
    op.drop_column("documents", "is_current")
    op.drop_column("documents", "version_number")
    op.drop_column("documents", "registry_id")
