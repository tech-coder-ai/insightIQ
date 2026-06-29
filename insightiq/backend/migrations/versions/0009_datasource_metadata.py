"""datasource metadata: description + approval status

Revision ID: 0009_datasource_metadata
Revises: 0008_extensions
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_datasource_metadata"
down_revision = "0008_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column("description", sa.Text(), server_default="", nullable=False),
    )
    op.add_column(
        "data_sources",
        sa.Column("metadata_status", sa.String(length=32), server_default="draft", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("data_sources", "metadata_status")
    op.drop_column("data_sources", "description")
