"""dashboards

Revision ID: 0005_dashboards
Revises: 0004_documents
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0005_dashboards"
down_revision = "0004_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("owner_user_id", uuid_col(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("global_filters_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("team_access_json", json_col(), server_default=json_array_default(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_dashboards_tenant_id", "dashboards", ["tenant_id"])
    op.create_index("ix_dashboards_owner_user_id", "dashboards", ["owner_user_id"])

    op.create_table(
        "dashboard_cards",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("dashboard_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("card_type", sa.String(length=64), nullable=False),
        sa.Column("layout_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("refresh_mode", sa.String(length=32), server_default="snapshot", nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_config_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("snapshot_response_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("auto_refresh_seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_dashboard_cards_dashboard_id", "dashboard_cards", ["dashboard_id"])

    op.create_table(
        "dashboard_shares",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("dashboard_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("read_only", sa.Boolean(), server_default=bool_default(True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
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
