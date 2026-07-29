"""backfill protected department catalog

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-29 15:30:00.000000

"""
from __future__ import annotations

from hashlib import sha256
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every persisted business department namespace is included.  Tables that
# derive scope through creator/reply foreign keys but have no department_code
# column (for example simulated_outbound_instructions) intentionally do not
# participate in this catalog backfill.
DEPARTMENT_CODE_TABLES = (
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


def _normalise_department_code(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _backfill_department_id(code: str) -> str:
    # Stable IDs make an interrupted local migration safe to rerun without
    # relying on random UUID generation or database-specific functions.
    return f"department_backfill_{sha256(code.encode('utf-8')).hexdigest()}"


def upgrade() -> None:
    bind = op.get_bind()
    catalog_codes = {
        code
        for (value,) in bind.execute(sa.text("SELECT code FROM departments"))
        if (code := _normalise_department_code(value))
    }
    business_codes: set[str] = set()
    for table_name in DEPARTMENT_CODE_TABLES:
        rows = bind.execute(sa.text(f"SELECT DISTINCT department_code FROM {table_name}"))
        business_codes.update(
            code for (value,) in rows if (code := _normalise_department_code(value))
        )

    for code in sorted(business_codes - catalog_codes):
        bind.execute(
            sa.text(
                "INSERT INTO departments (id, code, name, is_active) "
                "VALUES (:id, :code, :name, :is_active)"
            ),
            {
                "id": _backfill_department_id(code),
                "code": code,
                "name": code,
                "is_active": True,
            },
        )


def downgrade() -> None:
    # Intentionally do not delete catalog rows inserted by upgrade().  A later
    # membership or authorization audit may already refer to them; destructive
    # downgrade would break those records and silently change granted scope.
    pass
