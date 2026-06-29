"""scheduled reports + export tables

Revision ID: 0008_extensions
Revises: 0007_hardening
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_extensions"
down_revision = "0007_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default="3600", nullable=False),
        sa.Column("export_format", sa.String(length=16), server_default="pdf", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_scheduled_reports_tenant_id", "scheduled_reports", ["tenant_id"])
    op.create_index("ix_scheduled_reports_dashboard_id", "scheduled_reports", ["dashboard_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_reports_dashboard_id", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_tenant_id", table_name="scheduled_reports")
    op.drop_table("scheduled_reports")
