"""init

Revision ID: 0001_init
Revises: 
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from migrations.portable import bool_default, drop_pg_enum, json_array_default, json_col, json_object_default, now_default, user_role_column, uuid_col

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column("role", user_role_column(), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", uuid_col(), primary_key=True, nullable=False),
        sa.Column("tenant_id", uuid_col(), nullable=False),
        sa.Column("user_id", uuid_col(), nullable=False),
        sa.Column("conversation_id", uuid_col(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", json_col(), nullable=False, server_default=json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=now_default(), nullable=False),
    )
    op.create_index("ix_chat_messages_tenant_id", "chat_messages", ["tenant_id"], unique=False)
    op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"], unique=False)
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_user_id", table_name="chat_messages")
    op.drop_index("ix_chat_messages_tenant_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
    drop_pg_enum("role")

