"""add rbac foundation tables

Revision ID: d7e8f9a0b1c2
Revises: c4d5e6f7a8b9
Create Date: 2026-07-29 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("identity_source", sa.String(length=40), nullable=False),
        sa.Column("external_subject", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("identity_source", "external_subject", name="uq_auth_users_identity_source_subject"),
    )
    op.create_index("ix_auth_users_identity_source_active", "auth_users", ["identity_source", "is_active"])
    op.create_index("ix_auth_users_is_active", "auth_users", ["is_active"])
    op.create_index("ix_auth_users_created_at", "auth_users", ["created_at"])

    op.create_table(
        "departments",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_departments_code", "departments", ["code"])
    op.create_index("ix_departments_is_active", "departments", ["is_active"])
    op.create_index("ix_departments_created_at", "departments", ["created_at"])

    op.create_table(
        "user_department_memberships",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("auth_user_id", sa.String(length=120), nullable=False),
        sa.Column("department_id", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("authorization_source", sa.String(length=40), server_default="manual", nullable=False),
        sa.Column("granted_by_auth_user_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("role IN ('operator', 'reviewer', 'admin')", name="ck_user_department_memberships_role"),
        sa.ForeignKeyConstraint(["auth_user_id"], ["auth_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_auth_user_id"], ["auth_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("auth_user_id", "department_id", name="uq_user_department_memberships_user_department"),
    )
    op.create_index("ix_user_department_memberships_auth_user_id", "user_department_memberships", ["auth_user_id"])
    op.create_index("ix_user_department_memberships_department_id", "user_department_memberships", ["department_id"])
    op.create_index(
        "ix_user_department_memberships_granted_by_auth_user_id",
        "user_department_memberships",
        ["granted_by_auth_user_id"],
    )
    op.create_index("ix_user_department_memberships_is_active", "user_department_memberships", ["is_active"])
    op.create_index("ix_user_department_memberships_created_at", "user_department_memberships", ["created_at"])
    op.create_index(
        "ix_user_department_memberships_user_active",
        "user_department_memberships",
        ["auth_user_id", "is_active"],
    )
    op.create_index(
        "ix_user_department_memberships_department_active_role",
        "user_department_memberships",
        ["department_id", "is_active", "role"],
    )

    op.create_table(
        "authorization_audit_events",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor_auth_user_id", sa.String(length=120), nullable=True),
        sa.Column("target_auth_user_id", sa.String(length=120), nullable=True),
        sa.Column("department_id", sa.String(length=120), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["actor_auth_user_id"], ["auth_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["target_auth_user_id"], ["auth_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authorization_audit_events_action", "authorization_audit_events", ["action"])
    op.create_index("ix_authorization_audit_events_actor_auth_user_id", "authorization_audit_events", ["actor_auth_user_id"])
    op.create_index("ix_authorization_audit_events_target_auth_user_id", "authorization_audit_events", ["target_auth_user_id"])
    op.create_index("ix_authorization_audit_events_department_id", "authorization_audit_events", ["department_id"])
    op.create_index("ix_authorization_audit_events_created_at", "authorization_audit_events", ["created_at"])
    op.create_index(
        "ix_authorization_audit_events_actor_created",
        "authorization_audit_events",
        ["actor_auth_user_id", "created_at"],
    )
    op.create_index(
        "ix_authorization_audit_events_target_created",
        "authorization_audit_events",
        ["target_auth_user_id", "created_at"],
    )
    op.create_index(
        "ix_authorization_audit_events_department_created",
        "authorization_audit_events",
        ["department_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("authorization_audit_events")
    op.drop_table("user_department_memberships")
    op.drop_table("departments")
    op.drop_table("auth_users")
