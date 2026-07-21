"""add human review audit tables

Revision ID: 9c7a4d1e2b3f
Revises: 7f80855699a8
Create Date: 2026-07-20 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c7a4d1e2b3f"
down_revision: Union[str, Sequence[str], None] = "7f80855699a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 审核决定关联完整业务链路，且不声明 ondelete，避免删除原始审计证据。
    op.create_table(
        "human_review_decisions",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("creator_id", sa.String(length=120), nullable=False),
        sa.Column("inbound_reply_id", sa.String(length=120), nullable=False),
        sa.Column("agent_followup_run_id", sa.String(length=120), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=False),
        sa.Column("final_draft", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("decided_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["agent_followup_run_id"], ["agent_followup_runs.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["inbound_reply_id"], ["inbound_replies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_followup_run_id", name="uq_human_review_decisions_run"),
    )
    op.create_index(op.f("ix_human_review_decisions_actor_id"), "human_review_decisions", ["actor_id"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_created_at"), "human_review_decisions", ["created_at"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_creator_id"), "human_review_decisions", ["creator_id"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_decided_at"), "human_review_decisions", ["decided_at"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_department_code"), "human_review_decisions", ["department_code"], unique=False)
    op.create_index("ix_human_review_decisions_department_decided", "human_review_decisions", ["department_code", "decided_at"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_inbound_reply_id"), "human_review_decisions", ["inbound_reply_id"], unique=False)
    op.create_index(op.f("ix_human_review_decisions_outcome"), "human_review_decisions", ["outcome"], unique=False)

    # 导出记录保存当时的草稿文本；它表示人工交接，不表示系统已经发送消息。
    op.create_table(
        "draft_export_records",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("human_review_decision_id", sa.String(length=120), nullable=False),
        sa.Column("creator_id", sa.String(length=120), nullable=False),
        sa.Column("inbound_reply_id", sa.String(length=120), nullable=False),
        sa.Column("exported_content", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("exported_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"]),
        sa.ForeignKeyConstraint(["human_review_decision_id"], ["human_review_decisions.id"]),
        sa.ForeignKeyConstraint(["inbound_reply_id"], ["inbound_replies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_draft_export_records_actor_id"), "draft_export_records", ["actor_id"], unique=False)
    op.create_index(op.f("ix_draft_export_records_created_at"), "draft_export_records", ["created_at"], unique=False)
    op.create_index(op.f("ix_draft_export_records_creator_id"), "draft_export_records", ["creator_id"], unique=False)
    op.create_index(op.f("ix_draft_export_records_department_code"), "draft_export_records", ["department_code"], unique=False)
    op.create_index("ix_draft_export_records_department_exported", "draft_export_records", ["department_code", "exported_at"], unique=False)
    op.create_index(op.f("ix_draft_export_records_exported_at"), "draft_export_records", ["exported_at"], unique=False)
    op.create_index(op.f("ix_draft_export_records_human_review_decision_id"), "draft_export_records", ["human_review_decision_id"], unique=False)
    op.create_index(op.f("ix_draft_export_records_inbound_reply_id"), "draft_export_records", ["inbound_reply_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_draft_export_records_inbound_reply_id"), table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_human_review_decision_id"), table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_exported_at"), table_name="draft_export_records")
    op.drop_index("ix_draft_export_records_department_exported", table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_department_code"), table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_creator_id"), table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_created_at"), table_name="draft_export_records")
    op.drop_index(op.f("ix_draft_export_records_actor_id"), table_name="draft_export_records")
    op.drop_table("draft_export_records")

    op.drop_index(op.f("ix_human_review_decisions_outcome"), table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_inbound_reply_id"), table_name="human_review_decisions")
    op.drop_index("ix_human_review_decisions_department_decided", table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_department_code"), table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_decided_at"), table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_creator_id"), table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_created_at"), table_name="human_review_decisions")
    op.drop_index(op.f("ix_human_review_decisions_actor_id"), table_name="human_review_decisions")
    op.drop_table("human_review_decisions")
