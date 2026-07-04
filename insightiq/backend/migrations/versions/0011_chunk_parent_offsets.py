"""parent-child chunk offsets for RAG layout-aware chunking

Revision ID: 0011_chunk_parent_offsets
Revises: 0010_datasource_scope
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0011_chunk_parent_offsets"
down_revision = "0010_datasource_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("parent_char_start", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("parent_char_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "parent_char_end")
    op.drop_column("document_chunks", "parent_char_start")
