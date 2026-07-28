"""add review queue query indexes

Revision ID: c4d5e6f7a8b9
Revises: ab12cd34ef56
Create Date: 2026-07-28 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_inbound_replies_review_queue_status_created",
        "inbound_replies",
        ["processing_status", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_inbound_replies_review_queue_department_status_created",
        "inbound_replies",
        ["department_code", "processing_status", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_agent_followup_runs_review_queue_reply_created",
        "agent_followup_runs",
        ["inbound_reply_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_dnc_confirmations_review_queue_creator_created",
        "do_not_contact_confirmations",
        ["creator_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_human_review_decisions_review_queue_outcome_department_reply",
        "human_review_decisions",
        ["outcome", "department_code", "inbound_reply_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_human_review_decisions_review_queue_outcome_department_reply",
        table_name="human_review_decisions",
    )
    op.drop_index("ix_dnc_confirmations_review_queue_creator_created", table_name="do_not_contact_confirmations")
    op.drop_index("ix_agent_followup_runs_review_queue_reply_created", table_name="agent_followup_runs")
    op.drop_index("ix_inbound_replies_review_queue_department_status_created", table_name="inbound_replies")
    op.drop_index("ix_inbound_replies_review_queue_status_created", table_name="inbound_replies")
