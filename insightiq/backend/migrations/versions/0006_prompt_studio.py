"""prompt studio tables

Revision ID: 0006_prompt_studio
Revises: 0005_dashboards
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0006_prompt_studio"
down_revision = "0005_dashboards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("owner_user_id", uuid_col(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("bindings_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("is_shared", sa.Boolean(), server_default=bool_default(False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_prompt_templates_tenant_id", "prompt_templates", ["tenant_id"])

    op.create_table(
        "prompt_versions",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("template_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("variables_schema_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("created_by", uuid_col(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_prompt_versions_template_id", "prompt_versions", ["template_id"])

    op.create_table(
        "prompt_runs",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("template_id", uuid_col(), nullable=False),
        sa.Column("version_id", uuid_col(), nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("user_id", uuid_col(), nullable=False),
        sa.Column("variables_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("rendered_prompt", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        sa.Column("eval_scores_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("response_payload_json", json_col(), server_default=json_object_default(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_prompt_runs_template_id", "prompt_runs", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_prompt_runs_template_id", table_name="prompt_runs")
    op.drop_table("prompt_runs")
    op.drop_index("ix_prompt_versions_template_id", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index("ix_prompt_templates_tenant_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
