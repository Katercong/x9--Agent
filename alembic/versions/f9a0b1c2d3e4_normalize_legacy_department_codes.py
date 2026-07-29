"""normalize legacy department codes

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-07-29 16:15:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUSINESS_DEPARTMENT_CODE_TABLES = (
    "creators",
    "do_not_contact_confirmations",
    "inbound_replies",
    "outreach_emails",
    "creator_outreach_events",
    "followup_tasks",
    "agent_followup_runs",
    "human_review_decisions",
    "draft_export_records",
)


def _raise_if_blank_department_codes(bind: sa.Connection, table_name: str, column_name: str = "department_code") -> None:
    invalid_count = bind.scalar(
        sa.text(
            f"SELECT COUNT(*) FROM {table_name} "
            f"WHERE {column_name} IS NULL OR TRIM({column_name}) = ''"
        )
    )
    if invalid_count:
        raise RuntimeError(f"cannot normalize {table_name}: {invalid_count} blank department code(s)")


def _raise_if_department_catalog_would_collide(bind: sa.Connection) -> None:
    duplicate = bind.execute(
        sa.text(
            "SELECT LOWER(TRIM(code)) AS normalized_code "
            "FROM departments "
            "GROUP BY LOWER(TRIM(code)) "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot normalize departments: normalized catalog code collision")


def _raise_if_inbound_reply_scope_would_collide(bind: sa.Connection) -> None:
    """Protect the existing idempotency uniqueness before rewriting its scope key."""

    duplicate = bind.execute(
        sa.text(
            "SELECT LOWER(TRIM(department_code)) AS normalized_code "
            "FROM inbound_replies "
            "GROUP BY LOWER(TRIM(department_code)), channel, external_message_id "
            "HAVING COUNT(*) > 1 "
            "LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot normalize inbound_replies: idempotency key collision")


def upgrade() -> None:
    bind = op.get_bind()
    _raise_if_blank_department_codes(bind, "departments", "code")
    for table_name in BUSINESS_DEPARTMENT_CODE_TABLES:
        _raise_if_blank_department_codes(bind, table_name)
    _raise_if_department_catalog_would_collide(bind)
    _raise_if_inbound_reply_scope_would_collide(bind)

    # The initial catalog backfill created the canonical namespace.  Normalize
    # both catalog rows and business rows so exact SQL scope filters remain
    # aligned with that namespace after the upgrade.
    bind.execute(sa.text("UPDATE departments SET code = LOWER(TRIM(code)) WHERE code <> LOWER(TRIM(code))"))
    for table_name in BUSINESS_DEPARTMENT_CODE_TABLES:
        bind.execute(
            sa.text(
                f"UPDATE {table_name} "
                "SET department_code = LOWER(TRIM(department_code)) "
                "WHERE department_code <> LOWER(TRIM(department_code))"
            )
        )


def downgrade() -> None:
    # Original whitespace/casing is intentionally not restored.  It is neither
    # authorization-relevant nor reconstructable after a safe canonicalization.
    pass
