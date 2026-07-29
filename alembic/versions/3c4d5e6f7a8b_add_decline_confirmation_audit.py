"""add decline confirmation audit

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2026-07-29 21:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "3c4d5e6f7a8b"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decline_confirmations",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("creator_id", sa.String(length=120), nullable=False),
        sa.Column("inbound_reply_id", sa.String(length=120), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inbound_reply_id"], ["inbound_replies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("inbound_reply_id", name="uq_decline_confirmations_reply"),
    )
    op.create_index("ix_decline_confirmations_department_code", "decline_confirmations", ["department_code"])
    op.create_index("ix_decline_confirmations_creator_id", "decline_confirmations", ["creator_id"])
    op.create_index("ix_decline_confirmations_inbound_reply_id", "decline_confirmations", ["inbound_reply_id"])
    op.create_index("ix_decline_confirmations_actor_id", "decline_confirmations", ["actor_id"])
    op.create_index("ix_decline_confirmations_confirmed_at", "decline_confirmations", ["confirmed_at"])
    op.create_index("ix_decline_confirmations_created_at", "decline_confirmations", ["created_at"])
    op.create_index(
        "ix_decline_confirmations_department_confirmed",
        "decline_confirmations",
        ["department_code", "confirmed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_decline_confirmations_department_confirmed", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_created_at", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_confirmed_at", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_actor_id", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_inbound_reply_id", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_creator_id", table_name="decline_confirmations")
    op.drop_index("ix_decline_confirmations_department_code", table_name="decline_confirmations")
    op.drop_table("decline_confirmations")
