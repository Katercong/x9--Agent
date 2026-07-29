"""enforce portable ASCII department codes

Revision ID: 2b3c4d5e6f7a
Revises: 0a1b2c3d4e5f
Create Date: 2026-07-29 19:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.department_codes import validate_department_code


revision: str = "2b3c4d5e6f7a"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e5f"
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


def _canonical_rows(
    bind: sa.Connection,
    table_name: str,
    column_name: str = "department_code",
) -> list[tuple[str, str]]:
    """Read and validate every code before this migration writes anything."""

    rows = bind.execute(sa.text(f"SELECT id, {column_name} FROM {table_name}")).all()
    canonical_rows: list[tuple[str, str]] = []
    invalid_count = 0
    for record_id, value in rows:
        if not isinstance(value, str):
            invalid_count += 1
            continue
        try:
            canonical_rows.append((record_id, validate_department_code(value)))
        except ValueError:
            invalid_count += 1
    if invalid_count:
        raise RuntimeError(
            f"cannot normalize {table_name}: {invalid_count} department code(s) are not valid ASCII slugs"
        )
    return canonical_rows


def _raise_if_catalog_would_collide(rows: list[tuple[str, str]]) -> None:
    seen: dict[str, str] = {}
    for record_id, code in rows:
        existing_id = seen.setdefault(code, record_id)
        if existing_id != record_id:
            raise RuntimeError("cannot normalize departments: normalized catalog code collision")


def _raise_if_inbound_reply_scope_would_collide(bind: sa.Connection) -> None:
    """Protect idempotency uniqueness using Python's shared ASCII contract."""

    rows = bind.execute(
        sa.text("SELECT id, department_code, channel, external_message_id FROM inbound_replies")
    ).all()
    seen: set[tuple[str, str, str]] = set()
    invalid_count = 0
    for _record_id, value, channel, external_message_id in rows:
        if not isinstance(value, str):
            invalid_count += 1
            continue
        try:
            key = (validate_department_code(value), channel, external_message_id)
        except ValueError:
            invalid_count += 1
            continue
        if key in seen:
            raise RuntimeError("cannot normalize inbound_replies: idempotency key collision")
        seen.add(key)
    if invalid_count:
        raise RuntimeError(
            f"cannot normalize inbound_replies: {invalid_count} department code(s) are not valid ASCII slugs"
        )


def _write_canonical_rows(
    bind: sa.Connection,
    table_name: str,
    rows: list[tuple[str, str]],
    column_name: str = "department_code",
) -> None:
    if not rows:
        return
    bind.execute(
        sa.text(f"UPDATE {table_name} SET {column_name} = :code WHERE id = :id"),
        [{"id": record_id, "code": code} for record_id, code in rows],
    )


def upgrade() -> None:
    bind = op.get_bind()
    catalog_rows = _canonical_rows(bind, "departments", "code")
    business_rows = {
        table_name: _canonical_rows(bind, table_name)
        for table_name in BUSINESS_DEPARTMENT_CODE_TABLES
    }
    _raise_if_catalog_would_collide(catalog_rows)
    _raise_if_inbound_reply_scope_would_collide(bind)

    # Do not depend on database LOWER() for case conversion.  All rows have
    # passed the ASCII slug gate, and Python supplies the one canonical value
    # written to SQLite and PostgreSQL alike.
    _write_canonical_rows(bind, "departments", catalog_rows, "code")
    for table_name, rows in business_rows.items():
        _write_canonical_rows(bind, table_name, rows)


def downgrade() -> None:
    # Reintroducing non-canonical values would recreate authorization drift.
    pass
