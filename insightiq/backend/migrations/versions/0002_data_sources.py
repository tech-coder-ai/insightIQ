"""data sources

Revision ID: 0002_data_sources
Revises: 0001_init
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_data_sources"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("db_type", sa.String(length=64), nullable=False),
        sa.Column("connection_config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_data_sources_tenant_id", "data_sources", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_data_sources_tenant_id", table_name="data_sources")
    op.drop_table("data_sources")

