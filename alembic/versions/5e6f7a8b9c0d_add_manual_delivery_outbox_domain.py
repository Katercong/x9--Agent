"""add manual delivery outbox domain

Revision ID: 5e6f7a8b9c0d
Revises: 4d5e6f7a8b9c
Create Date: 2026-07-30 12:00:00.000000

The outbox is deliberately credential-free and has no network side effects.
It records reviewed-draft snapshots and two-person-in-time confirmation state;
Gmail OAuth and a delivery worker are separate future work.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5e6f7a8b9c0d"
down_revision: Union[str, Sequence[str], None] = "4d5e6f7a8b9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manual_delivery_accounts",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("owner_auth_user_id", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), server_default=sa.text("40"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("daily_limit >= 1", name="ck_manual_delivery_accounts_positive_daily_limit"),
        sa.ForeignKeyConstraint(["owner_auth_user_id"], ["auth_users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_manual_delivery_accounts_email"),
    )
    op.create_index("ix_manual_delivery_accounts_department_code", "manual_delivery_accounts", ["department_code"])
    op.create_index("ix_manual_delivery_accounts_owner_auth_user_id", "manual_delivery_accounts", ["owner_auth_user_id"])
    op.create_index("ix_manual_delivery_accounts_email", "manual_delivery_accounts", ["email"])
    op.create_index("ix_manual_delivery_accounts_is_active", "manual_delivery_accounts", ["is_active"])
    op.create_index("ix_manual_delivery_accounts_created_at", "manual_delivery_accounts", ["created_at"])
    op.create_index(
        "ix_manual_delivery_accounts_department_owner_active",
        "manual_delivery_accounts",
        ["department_code", "owner_auth_user_id", "is_active"],
    )

    op.create_table(
        "manual_delivery_daily_quotas",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("manual_delivery_account_id", sa.String(length=120), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("reserved_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("reserved_count >= 0", name="ck_manual_delivery_daily_quotas_non_negative"),
        sa.ForeignKeyConstraint(["manual_delivery_account_id"], ["manual_delivery_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manual_delivery_account_id", "quota_date", name="uq_manual_delivery_daily_quotas_account_date"),
    )
    op.create_index("ix_manual_delivery_daily_quotas_manual_delivery_account_id", "manual_delivery_daily_quotas", ["manual_delivery_account_id"])
    op.create_index("ix_manual_delivery_daily_quotas_quota_date", "manual_delivery_daily_quotas", ["quota_date"])
    op.create_index("ix_manual_delivery_daily_quotas_created_at", "manual_delivery_daily_quotas", ["created_at"])

    op.create_table(
        "manual_delivery_requests",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("human_review_decision_id", sa.String(length=120), nullable=False),
        sa.Column("creator_id", sa.String(length=120), nullable=False),
        sa.Column("inbound_reply_id", sa.String(length=120), nullable=False),
        sa.Column("manual_delivery_account_id", sa.String(length=120), nullable=True),
        sa.Column("draft_content_snapshot", sa.Text(), nullable=False),
        sa.Column("draft_sha256", sa.String(length=64), nullable=False),
        sa.Column("recipient_email_snapshot", sa.String(length=320), nullable=True),
        sa.Column("subject_snapshot", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("gmail_thread_id_snapshot", sa.String(length=320), nullable=True),
        sa.Column("rfc_message_id_snapshot", sa.String(length=1000), nullable=True),
        sa.Column("references_snapshot", sa.Text(), nullable=True),
        sa.Column("approved_by_auth_user_id", sa.String(length=120), nullable=False),
        sa.Column("second_confirmed_by_auth_user_id", sa.String(length=120), nullable=True),
        sa.Column("account_email_snapshot", sa.String(length=320), nullable=True),
        sa.Column("account_owner_auth_user_id_snapshot", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), server_default=sa.text("'pending_second_confirmation'"), nullable=False),
        sa.Column("status_reason", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("quota_reserved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("quota_reservation_date", sa.Date(), nullable=True),
        sa.Column("second_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("sending_started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending_second_confirmation', 'queued', 'sending', 'sent', 'failed', 'unknown', 'expired', 'blocked_by_dnc')",
            name="ck_manual_delivery_requests_status",
        ),
        sa.ForeignKeyConstraint(["human_review_decision_id"], ["human_review_decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["creator_id"], ["creators.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inbound_reply_id"], ["inbound_replies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manual_delivery_account_id"], ["manual_delivery_accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("human_review_decision_id", name="uq_manual_delivery_requests_decision"),
    )
    for column in (
        "department_code",
        "human_review_decision_id",
        "creator_id",
        "inbound_reply_id",
        "manual_delivery_account_id",
        "status",
        "expires_at",
        "quota_reserved",
        "quota_reservation_date",
        "second_confirmed_by_auth_user_id",
        "second_confirmed_at",
        "queued_at",
        "sending_started_at",
        "completed_at",
        "created_at",
    ):
        op.create_index(f"ix_manual_delivery_requests_{column}", "manual_delivery_requests", [column])
    op.create_index(
        "ix_manual_delivery_requests_department_status_created",
        "manual_delivery_requests",
        ["department_code", "status", "created_at"],
    )
    op.create_index("ix_manual_delivery_requests_creator_status", "manual_delivery_requests", ["creator_id", "status"])
    op.create_index("ix_manual_delivery_requests_expiry_status", "manual_delivery_requests", ["expires_at", "status"])

    op.create_table(
        "manual_delivery_events",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("manual_delivery_request_id", sa.String(length=120), nullable=False),
        sa.Column("department_code", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("event_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["manual_delivery_request_id"], ["manual_delivery_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("manual_delivery_request_id", "department_code", "actor_id", "event_type", "event_at", "created_at"):
        op.create_index(f"ix_manual_delivery_events_{column}", "manual_delivery_events", [column])
    op.create_index(
        "ix_manual_delivery_events_request_event_at",
        "manual_delivery_events",
        ["manual_delivery_request_id", "event_at"],
    )
    op.create_index(
        "ix_manual_delivery_events_department_event_at",
        "manual_delivery_events",
        ["department_code", "event_at"],
    )
    _create_manual_delivery_guards()


def downgrade() -> None:
    _drop_manual_delivery_guards()
    op.drop_index("ix_manual_delivery_events_department_event_at", table_name="manual_delivery_events")
    op.drop_index("ix_manual_delivery_events_request_event_at", table_name="manual_delivery_events")
    for column in ("created_at", "event_at", "event_type", "actor_id", "department_code", "manual_delivery_request_id"):
        op.drop_index(f"ix_manual_delivery_events_{column}", table_name="manual_delivery_events")
    op.drop_table("manual_delivery_events")

    op.drop_index("ix_manual_delivery_requests_expiry_status", table_name="manual_delivery_requests")
    op.drop_index("ix_manual_delivery_requests_creator_status", table_name="manual_delivery_requests")
    op.drop_index("ix_manual_delivery_requests_department_status_created", table_name="manual_delivery_requests")
    for column in (
        "created_at",
        "completed_at",
        "sending_started_at",
        "queued_at",
        "second_confirmed_at",
        "second_confirmed_by_auth_user_id",
        "quota_reservation_date",
        "quota_reserved",
        "expires_at",
        "status",
        "manual_delivery_account_id",
        "inbound_reply_id",
        "creator_id",
        "human_review_decision_id",
        "department_code",
    ):
        op.drop_index(f"ix_manual_delivery_requests_{column}", table_name="manual_delivery_requests")
    op.drop_table("manual_delivery_requests")

    op.drop_index("ix_manual_delivery_daily_quotas_created_at", table_name="manual_delivery_daily_quotas")
    op.drop_index("ix_manual_delivery_daily_quotas_quota_date", table_name="manual_delivery_daily_quotas")
    op.drop_index("ix_manual_delivery_daily_quotas_manual_delivery_account_id", table_name="manual_delivery_daily_quotas")
    op.drop_table("manual_delivery_daily_quotas")

    op.drop_index("ix_manual_delivery_accounts_department_owner_active", table_name="manual_delivery_accounts")
    op.drop_index("ix_manual_delivery_accounts_created_at", table_name="manual_delivery_accounts")
    op.drop_index("ix_manual_delivery_accounts_is_active", table_name="manual_delivery_accounts")
    op.drop_index("ix_manual_delivery_accounts_email", table_name="manual_delivery_accounts")
    op.drop_index("ix_manual_delivery_accounts_owner_auth_user_id", table_name="manual_delivery_accounts")
    op.drop_index("ix_manual_delivery_accounts_department_code", table_name="manual_delivery_accounts")
    op.drop_table("manual_delivery_accounts")


def _create_manual_delivery_guards() -> None:
    """Freeze snapshots and events at the PostgreSQL persistence boundary."""

    op.execute(
        """
        CREATE FUNCTION prevent_manual_delivery_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'manual delivery events are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_manual_delivery_events_no_update
        BEFORE UPDATE ON manual_delivery_events
        FOR EACH ROW EXECUTE FUNCTION prevent_manual_delivery_event_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_manual_delivery_events_no_delete
        BEFORE DELETE ON manual_delivery_events
        FOR EACH ROW EXECUTE FUNCTION prevent_manual_delivery_event_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION prevent_manual_delivery_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.human_review_decision_id IS DISTINCT FROM OLD.human_review_decision_id
               OR NEW.creator_id IS DISTINCT FROM OLD.creator_id
               OR NEW.inbound_reply_id IS DISTINCT FROM OLD.inbound_reply_id
               OR NEW.draft_content_snapshot IS DISTINCT FROM OLD.draft_content_snapshot
               OR NEW.draft_sha256 IS DISTINCT FROM OLD.draft_sha256
               OR NEW.recipient_email_snapshot IS DISTINCT FROM OLD.recipient_email_snapshot
               OR NEW.subject_snapshot IS DISTINCT FROM OLD.subject_snapshot
               OR NEW.gmail_thread_id_snapshot IS DISTINCT FROM OLD.gmail_thread_id_snapshot
               OR NEW.rfc_message_id_snapshot IS DISTINCT FROM OLD.rfc_message_id_snapshot
               OR NEW.references_snapshot IS DISTINCT FROM OLD.references_snapshot
               OR NEW.approved_by_auth_user_id IS DISTINCT FROM OLD.approved_by_auth_user_id
               OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
            THEN
                RAISE EXCEPTION 'manual delivery request snapshots are immutable';
            END IF;
            IF OLD.manual_delivery_account_id IS NOT NULL
               AND (NEW.manual_delivery_account_id IS DISTINCT FROM OLD.manual_delivery_account_id
                    OR NEW.account_email_snapshot IS DISTINCT FROM OLD.account_email_snapshot
                    OR NEW.account_owner_auth_user_id_snapshot IS DISTINCT FROM OLD.account_owner_auth_user_id_snapshot
                    OR NEW.second_confirmed_by_auth_user_id IS DISTINCT FROM OLD.second_confirmed_by_auth_user_id
                    OR NEW.second_confirmed_at IS DISTINCT FROM OLD.second_confirmed_at)
            THEN
                RAISE EXCEPTION 'manual delivery confirmation account is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_manual_delivery_requests_snapshot_immutable
        BEFORE UPDATE ON manual_delivery_requests
        FOR EACH ROW EXECUTE FUNCTION prevent_manual_delivery_snapshot_mutation();
        """
    )


def _drop_manual_delivery_guards() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_manual_delivery_requests_snapshot_immutable ON manual_delivery_requests")
    op.execute("DROP FUNCTION IF EXISTS prevent_manual_delivery_snapshot_mutation()")
    op.execute("DROP TRIGGER IF EXISTS trg_manual_delivery_events_no_delete ON manual_delivery_events")
    op.execute("DROP TRIGGER IF EXISTS trg_manual_delivery_events_no_update ON manual_delivery_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_manual_delivery_event_mutation()")
