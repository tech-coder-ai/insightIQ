"""datasource selected table/column scope

Revision ID: 0010_datasource_scope
Revises: 0009_datasource_metadata
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0010_datasource_scope"
down_revision = "0009_datasource_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "data_sources",
        sa.Column("selected_scope_json", json_col(), server_default=json_object_default(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("data_sources", "selected_scope_json")
