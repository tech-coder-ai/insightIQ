"""dashboards

Revision ID: 0005_dashboards
Revises: 0004_documents
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0005_dashboards"
down_revision = "0004_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("global_filters_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("team_access_json", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_dashboards_tenant_id", "dashboards", ["tenant_id"])
    op.create_index("ix_dashboards_owner_user_id", "dashboards", ["owner_user_id"])

    op.create_table(
        "dashboard_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("card_type", sa.String(length=64), nullable=False),
        sa.Column("layout_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("refresh_mode", sa.String(length=32), server_default="snapshot", nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_config_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("snapshot_response_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("auto_refresh_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_dashboard_cards_dashboard_id", "dashboard_cards", ["dashboard_id"])

    op.create_table(
        "dashboard_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("read_only", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_dashboard_shares_token", "dashboard_shares", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_dashboard_shares_token", table_name="dashboard_shares")
    op.drop_table("dashboard_shares")
    op.drop_index("ix_dashboard_cards_dashboard_id", table_name="dashboard_cards")
    op.drop_table("dashboard_cards")
    op.drop_index("ix_dashboards_owner_user_id", table_name="dashboards")
    op.drop_index("ix_dashboards_tenant_id", table_name="dashboards")
    op.drop_table("dashboards")
