"""phase 2 schema

Revision ID: 0003_phase2
Revises: 0002_data_sources
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_phase2"
down_revision = "0002_data_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("data_sources", sa.Column("dialect", sa.String(length=64), server_default="postgres"))
    op.add_column(
        "data_sources",
        sa.Column("schema_snapshot_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "data_sources",
        sa.Column("relationships_json", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "data_sources",
        sa.Column("glossary_json", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), server_default="New conversation", nullable=False),
        sa.Column("folder", sa.String(length=200), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("starred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("datasource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversations_tenant_id", "conversations", ["tenant_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_index("ix_conversations_tenant_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_column("data_sources", "glossary_json")
    op.drop_column("data_sources", "relationships_json")
    op.drop_column("data_sources", "schema_snapshot_json")
    op.drop_column("data_sources", "dialect")
