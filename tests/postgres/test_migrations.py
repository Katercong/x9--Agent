"""Historical Alembic paths exercised against disposable PostgreSQL databases."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import sessionmaker

from app.models import Creator, InboundReply


pytestmark = pytest.mark.postgres_integration


def _assert_success(result) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_postgresql_empty_database_upgrades_to_current_head(
    temporary_postgres_database: str,
    run_alembic,
    postgres_engine,
):
    """Every committed revision must apply to an empty PostgreSQL database."""

    result = run_alembic(temporary_postgres_database, "upgrade", "head")
    _assert_success(result)
    migration_engine = create_engine(temporary_postgres_database, future=True)
    try:
        with migration_engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        with postgres_engine.connect() as connection:
            expected_head = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == expected_head
    finally:
        migration_engine.dispose()


def test_postgresql_department_backfill_normalizes_historical_scope_without_destructive_downgrade(
    temporary_postgres_database: str,
    run_alembic,
):
    """Historical code remains readable after backfill and all later canonicalization revisions."""

    _assert_success(run_alembic(temporary_postgres_database, "upgrade", "d7e8f9a0b1c2"))
    migration_engine = create_engine(temporary_postgres_database, future=True)
    MigrationSession = sessionmaker(bind=migration_engine, future=True)
    try:
        with MigrationSession() as db:
            creator = Creator(id="pg_backfill_creator", department_code="\tForeign_Trade\n", handle="pg_backfill_creator")
            reply = InboundReply(
                id="pg_backfill_reply",
                department_code="\tForeign_Trade\n",
                creator_id=creator.id,
                direction="inbound",
                channel="postgres_migration",
                external_message_id="pg-backfill-reply",
                body="Backfill reply",
                processing_status="need_ai_review",
            )
            db.add_all([creator, reply])
            db.commit()

        _assert_success(run_alembic(temporary_postgres_database, "upgrade", "head"))
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT code FROM departments WHERE code = 'foreign_trade'")) == "foreign_trade"
            assert connection.scalar(text("SELECT department_code FROM creators WHERE id = 'pg_backfill_creator'")) == "foreign_trade"
            assert connection.scalar(text("SELECT department_code FROM inbound_replies WHERE id = 'pg_backfill_reply'")) == "foreign_trade"

        _assert_success(run_alembic(temporary_postgres_database, "downgrade", "d7e8f9a0b1c2"))
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT code FROM departments WHERE code = 'foreign_trade'")) == "foreign_trade"
    finally:
        migration_engine.dispose()


def test_postgresql_ascii_department_migration_blocks_non_ascii_historical_scope(
    temporary_postgres_database: str,
    run_alembic,
):
    """The frozen migration chain must reject non-ASCII data on PostgreSQL too."""

    _assert_success(run_alembic(temporary_postgres_database, "upgrade", "d7e8f9a0b1c2"))
    migration_engine = create_engine(temporary_postgres_database, future=True)
    MigrationSession = sessionmaker(bind=migration_engine, future=True)
    try:
        with MigrationSession() as db:
            creator = Creator(id="pg_non_ascii_creator", department_code="\tÄPFEL\n", handle="pg_non_ascii_creator")
            reply = InboundReply(
                id="pg_non_ascii_reply",
                department_code=creator.department_code,
                creator_id=creator.id,
                direction="inbound",
                channel="postgres_migration",
                external_message_id="pg-non-ascii-reply",
                body="Non-ASCII legacy department code.",
                processing_status="need_ai_review",
            )
            db.add_all([creator, reply])
            db.commit()

        result = run_alembic(temporary_postgres_database, "upgrade", "head")
        assert result.returncode != 0
        assert "department code(s) are not valid ASCII slugs" in result.stdout + result.stderr
        with migration_engine.connect() as connection:
            # PostgreSQL applies the chained Alembic upgrades transactionally:
            # the strict ASCII gate rolls the entire attempt back to the
            # starting historical revision instead of leaving a partial head.
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "d7e8f9a0b1c2"
            assert connection.scalar(
                text("SELECT department_code FROM inbound_replies WHERE id = 'pg_non_ascii_reply'")
            ) == "\tÄPFEL\n"
    finally:
        migration_engine.dispose()


def test_postgresql_decline_and_worker_audit_migrations_apply_database_guards_and_downgrade(
    temporary_postgres_database: str,
    run_alembic,
):
    """Audit tables, restrictive keys and immutable-event triggers are real PostgreSQL DDL."""

    _assert_success(run_alembic(temporary_postgres_database, "upgrade", "head"))
    migration_engine = create_engine(temporary_postgres_database, future=True)
    try:
        with migration_engine.begin() as connection:
            trigger_names = set(
                connection.scalars(
                    text(
                        "SELECT tgname FROM pg_trigger "
                        "WHERE tgrelid = 'worker_run_events'::regclass AND NOT tgisinternal"
                    )
                )
            )
            assert {"trg_worker_run_events_no_update", "trg_worker_run_events_no_delete"} <= trigger_names
            assert connection.scalar(text("SELECT to_regclass('decline_confirmations')")) == "decline_confirmations"
            decline_constraints = set(
                connection.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'decline_confirmations'::regclass"
                    )
                )
            )
            assert "uq_decline_confirmations_reply" in decline_constraints
            connection.execute(
                text(
                    "INSERT INTO creators (id, department_code, platform, handle, do_not_contact_status) "
                    "VALUES ('pg_migration_creator', 'cross_border', 'instagram', 'pg_migration_creator', 'none')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO inbound_replies "
                    "(id, department_code, creator_id, direction, channel, external_message_id, from_email, to_email, subject, body, body_format, processing_status) "
                    "VALUES ('pg_migration_reply', 'cross_border', 'pg_migration_creator', 'inbound', 'postgres_migration', "
                    "'pg-migration-message', '', '', '', 'Migration reply', 'text', 'need_ai_review')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO agent_followup_runs "
                    "(id, department_code, creator_id, inbound_reply_id, llm_status, execution_status) "
                    "VALUES ('pg_migration_run', 'cross_border', 'pg_migration_creator', 'pg_migration_reply', 'not_configured', 'succeeded')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO worker_run_events (id, agent_followup_run_id, department_code, worker_id, event_type) "
                    "VALUES ('pg_migration_event', 'pg_migration_run', 'cross_border', 'pg_migration_worker', 'claim_acquired')"
                )
            )

        with pytest.raises(DatabaseError, match="worker run events are immutable"):
            with migration_engine.begin() as connection:
                connection.execute(
                    text("UPDATE worker_run_events SET event_type = 'tampered' WHERE id = 'pg_migration_event'")
                )

        _assert_success(run_alembic(temporary_postgres_database, "downgrade", "2b3c4d5e6f7a"))
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('worker_run_events')")) is None
            assert connection.scalar(text("SELECT to_regclass('decline_confirmations')")) is None
            assert connection.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_name = 'agent_followup_runs' AND column_name = 'claimed_by_worker_id'"
                )
            ) == 0
    finally:
        migration_engine.dispose()
