"""scheduled reports + export tables

Revision ID: 0008_extensions
Revises: 0007_hardening
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0008_extensions"
down_revision = "0007_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_reports",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("dashboard_id", uuid_col(), nullable=False),
        sa.Column("owner_user_id", uuid_col(), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default="3600", nullable=False),
        sa.Column("export_format", sa.String(length=16), server_default="pdf", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=bool_default(True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_scheduled_reports_tenant_id", "scheduled_reports", ["tenant_id"])
    op.create_index("ix_scheduled_reports_dashboard_id", "scheduled_reports", ["dashboard_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_reports_dashboard_id", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_tenant_id", table_name="scheduled_reports")
    op.drop_table("scheduled_reports")
