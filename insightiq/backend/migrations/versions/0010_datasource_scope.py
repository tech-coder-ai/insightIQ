"""datasource selected table/column scope

Revision ID: 0010_datasource_scope
Revises: 0009_datasource_metadata
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0010_datasource_scope"
down_revision = "0009_datasource_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column("selected_scope_json", JSONB, server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("data_sources", "selected_scope_json")
