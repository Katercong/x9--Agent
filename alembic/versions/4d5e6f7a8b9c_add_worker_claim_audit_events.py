"""add worker claim audit events

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2026-07-29 22:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, Sequence[str], None] = "3c4d5e6f7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agent_followup_runs",
        sa.Column("claimed_by_worker_id", sa.String(length=200), nullable=True),
    )
    op.create_index(
        "ix_agent_followup_runs_claimed_by_worker_id",
        "agent_followup_runs",
        ["claimed_by_worker_id"],
    )
    op.create_table(
        "worker_run_events",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("agent_followup_run_id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("event_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["agent_followup_run_id"], ["agent_followup_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_run_events_agent_followup_run_id", "worker_run_events", ["agent_followup_run_id"])
    op.create_index("ix_worker_run_events_department_code", "worker_run_events", ["department_code"])
    op.create_index("ix_worker_run_events_worker_id", "worker_run_events", ["worker_id"])
    op.create_index("ix_worker_run_events_event_type", "worker_run_events", ["event_type"])
    op.create_index("ix_worker_run_events_event_at", "worker_run_events", ["event_at"])
    op.create_index("ix_worker_run_events_created_at", "worker_run_events", ["created_at"])
    op.create_index(
        "ix_worker_run_events_run_event_at",
        "worker_run_events",
        ["agent_followup_run_id", "event_at"],
    )
    op.create_index(
        "ix_worker_run_events_department_event_at",
        "worker_run_events",
        ["department_code", "event_at"],
    )
    op.create_index(
        "ix_worker_run_events_type_event_at",
        "worker_run_events",
        ["event_type", "event_at"],
    )
    _create_immutable_event_guards()


def downgrade() -> None:
    _drop_immutable_event_guards()
    op.drop_index("ix_worker_run_events_type_event_at", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_department_event_at", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_run_event_at", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_created_at", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_event_at", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_event_type", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_worker_id", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_department_code", table_name="worker_run_events")
    op.drop_index("ix_worker_run_events_agent_followup_run_id", table_name="worker_run_events")
    op.drop_table("worker_run_events")
    op.drop_index("ix_agent_followup_runs_claimed_by_worker_id", table_name="agent_followup_runs")
    op.drop_column("agent_followup_runs", "claimed_by_worker_id")


def _create_immutable_event_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION prevent_worker_run_event_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'worker run events are immutable';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_worker_run_events_no_update
            BEFORE UPDATE ON worker_run_events
            FOR EACH ROW EXECUTE FUNCTION prevent_worker_run_event_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_worker_run_events_no_delete
            BEFORE DELETE ON worker_run_events
            FOR EACH ROW EXECUTE FUNCTION prevent_worker_run_event_mutation();
            """
        )
        return
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_worker_run_events_no_update
            BEFORE UPDATE ON worker_run_events
            BEGIN
                SELECT RAISE(ABORT, 'worker run events are immutable');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_worker_run_events_no_delete
            BEFORE DELETE ON worker_run_events
            BEGIN
                SELECT RAISE(ABORT, 'worker run events are immutable');
            END;
            """
        )


def _drop_immutable_event_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_worker_run_events_no_delete ON worker_run_events")
        op.execute("DROP TRIGGER IF EXISTS trg_worker_run_events_no_update ON worker_run_events")
        op.execute("DROP FUNCTION IF EXISTS prevent_worker_run_event_mutation()")
        return
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_worker_run_events_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_worker_run_events_no_update")
