"""document collections and RAG tables

Revision ID: 0004_documents
Revises: 0003_phase2
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0004_documents"
down_revision = "0003_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_collections",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("rag_profile", sa.String(length=64), server_default="naive", nullable=False),
        sa.Column("embedding_model", sa.String(length=128), server_default="hash-dev", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_document_collections_tenant_id", "document_collections", ["tenant_id"])

    op.create_table(
        "documents",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("collection_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("content_markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("metadata_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_documents_collection_id", "documents", ["collection_id"])
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("document_id", uuid_col(), nullable=False),
        sa.Column("collection_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("qdrant_point_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_collection_id", "document_chunks", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_document_chunks_collection_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_tenant_id", table_name="documents")
    op.drop_index("ix_documents_collection_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_document_collections_tenant_id", table_name="document_collections")
    op.drop_table("document_collections")
