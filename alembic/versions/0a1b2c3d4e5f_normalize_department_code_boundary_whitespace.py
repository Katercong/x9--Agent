"""normalize department code boundary whitespace

Revision ID: 0a1b2c3d4e5f
Revises: f9a0b1c2d3e4
Create Date: 2026-07-29 18:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.department_codes import normalised_department_code_expression


revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
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


def _department_code_table(table_name: str, column_name: str = "department_code") -> sa.TableClause:
    return sa.table(table_name, sa.column(column_name, sa.String()))


def _normalised_code(
    bind: sa.Connection,
    table: sa.TableClause,
    column_name: str,
) -> sa.ColumnElement[str]:
    return normalised_department_code_expression(
        table.c[column_name],
        dialect_name=bind.dialect.name,
    )


def _raise_if_blank_department_codes(
    bind: sa.Connection,
    table_name: str,
    column_name: str = "department_code",
) -> None:
    table = _department_code_table(table_name, column_name)
    column = table.c[column_name]
    normalised = _normalised_code(bind, table, column_name)
    invalid_count = bind.scalar(
        sa.select(sa.func.count())
        .select_from(table)
        .where(sa.or_(column.is_(None), normalised == ""))
    )
    if invalid_count:
        raise RuntimeError(f"cannot normalize {table_name}: {invalid_count} blank department code(s)")


def _raise_if_department_catalog_would_collide(bind: sa.Connection) -> None:
    departments = _department_code_table("departments", "code")
    normalised = _normalised_code(bind, departments, "code")
    duplicate = bind.execute(
        sa.select(normalised.label("normalized_code"))
        .select_from(departments)
        .group_by(normalised)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot normalize departments: normalized catalog code collision")


def _raise_if_inbound_reply_scope_would_collide(bind: sa.Connection) -> None:
    """Protect idempotency uniqueness before rewriting its department scope."""

    inbound_replies = sa.table(
        "inbound_replies",
        sa.column("department_code", sa.String()),
        sa.column("channel", sa.String()),
        sa.column("external_message_id", sa.String()),
    )
    normalised = _normalised_code(bind, inbound_replies, "department_code")
    duplicate = bind.execute(
        sa.select(normalised.label("normalized_code"))
        .select_from(inbound_replies)
        .group_by(normalised, inbound_replies.c.channel, inbound_replies.c.external_message_id)
        .having(sa.func.count() > 1)
        .limit(1)
    ).first()
    if duplicate is not None:
        raise RuntimeError("cannot normalize inbound_replies: idempotency key collision")


def _normalise_table_codes(bind: sa.Connection, table_name: str, column_name: str = "department_code") -> None:
    table = _department_code_table(table_name, column_name)
    normalised = _normalised_code(bind, table, column_name)
    bind.execute(
        sa.update(table)
        .where(table.c[column_name] != normalised)
        .values({column_name: normalised})
    )


def upgrade() -> None:
    bind = op.get_bind()
    _raise_if_blank_department_codes(bind, "departments", "code")
    for table_name in BUSINESS_DEPARTMENT_CODE_TABLES:
        _raise_if_blank_department_codes(bind, table_name)
    _raise_if_department_catalog_would_collide(bind)
    _raise_if_inbound_reply_scope_would_collide(bind)

    # The preceding revision predates the explicit boundary character set and
    # only trims ordinary spaces.  This forward-only repair applies the shared
    # API/migration rule to both namespaces before strict scope filters run.
    _normalise_table_codes(bind, "departments", "code")
    for table_name in BUSINESS_DEPARTMENT_CODE_TABLES:
        _normalise_table_codes(bind, table_name)


def downgrade() -> None:
    # Canonical values cannot safely be expanded back into their former
    # whitespace representation; keeping them prevents access-scope drift.
    pass
