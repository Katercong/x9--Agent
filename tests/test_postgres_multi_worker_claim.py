"""Explicit PostgreSQL concurrency coverage for the Worker claim protocol.

Run only against an isolated database, for example after starting a temporary
Docker Compose PostgreSQL service:

    RUN_POSTGRES_INTEGRATION=1 POSTGRES_INTEGRATION_DATABASE_URL=... \
        python -m pytest -q tests/test_postgres_multi_worker_claim.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import services
from app.models import AgentFollowupRun, Creator, InboundReply, SimulatedOutboundInstruction, WorkerRunEvent


pytestmark = pytest.mark.postgres_integration


@pytest.fixture(scope="module")
def postgres_sessions() -> sessionmaker[Session]:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL concurrency coverage")
    database_url = os.getenv("POSTGRES_INTEGRATION_DATABASE_URL")
    if not database_url:
        pytest.fail("POSTGRES_INTEGRATION_DATABASE_URL must point to an isolated PostgreSQL database")

    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    migrated = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert migrated.returncode == 0, migrated.stdout + migrated.stderr

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql"
    try:
        yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    finally:
        engine.dispose()


def _seed_run(
    sessions: sessionmaker[Session],
    *,
    suffix: str,
    execution_status: str = "queued",
    lease_expires_at: datetime | None = None,
    claim_token: str | None = None,
    claimed_by_worker_id: str | None = None,
) -> AgentFollowupRun:
    creator_id = f"pg_creator_{suffix}"
    reply_id = f"pg_reply_{suffix}"
    run = AgentFollowupRun(
        id=f"pg_run_{suffix}",
        department_code="cross_border",
        creator_id=creator_id,
        inbound_reply_id=reply_id,
        llm_status="not_configured",
        execution_status=execution_status,
        started_at=datetime.utcnow() - timedelta(seconds=5) if execution_status == "running" else None,
        claim_token=claim_token,
        claimed_by_worker_id=claimed_by_worker_id,
        lease_expires_at=lease_expires_at,
    )
    with sessions() as db:
        # The ORM models intentionally do not define relationship properties;
        # flush parents explicitly so PostgreSQL checks the audit foreign keys
        # in the same order a real ingestion flow writes them.
        db.add(Creator(id=creator_id, department_code="cross_border", handle=f"pg_handle_{suffix}"))
        db.flush()
        db.add(
            InboundReply(
                id=reply_id,
                department_code="cross_border",
                creator_id=creator_id,
                direction="inbound",
                channel="postgres_integration",
                external_message_id=f"pg_external_{suffix}",
                body="PostgreSQL worker concurrency test message.",
                processing_status="need_ai_review",
            )
        )
        db.flush()
        db.add(run)
        db.commit()
        db.refresh(run)
        return run


def test_postgresql_multi_worker_claim_recovery_and_stale_result_protection(
    postgres_sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
):
    """Exercise SKIP LOCKED with real transactions; neither LLM nor outbound work is involved."""

    prefix = uuid.uuid4().hex[:12]
    first_queued = _seed_run(postgres_sessions, suffix=f"{prefix}_first")
    second_queued = _seed_run(postgres_sessions, suffix=f"{prefix}_second")

    first_worker = postgres_sessions()
    second_worker = postgres_sessions()
    try:
        first_claim = services.claim_next_queued_run(first_worker, worker_id="postgres_worker_one")
        assert first_claim is not None
        # Keep this update uncommitted.  The next transaction must skip its row
        # and claim the second queued run rather than blocking or duplicating it.
        second_claim = services.claim_next_queued_run(second_worker, worker_id="postgres_worker_two")
        assert second_claim is not None
        assert {first_claim.run_id, second_claim.run_id} == {first_queued.id, second_queued.id}
        assert first_claim.run_id != second_claim.run_id
        second_worker.commit()
        first_worker.commit()
    finally:
        second_worker.close()
        first_worker.close()

    only_queued = _seed_run(postgres_sessions, suffix=f"{prefix}_only")
    first_worker = postgres_sessions()
    second_worker = postgres_sessions()
    try:
        only_claim = services.claim_next_queued_run(first_worker, worker_id="postgres_worker_three")
        assert only_claim is not None and only_claim.run_id == only_queued.id
        assert services.claim_next_queued_run(second_worker, worker_id="postgres_worker_four") is None
        second_worker.commit()
        first_worker.commit()
    finally:
        second_worker.close()
        first_worker.close()

    expired = _seed_run(
        postgres_sessions,
        suffix=f"{prefix}_expired",
        execution_status="running",
        claim_token="expired-claim-token",
        claimed_by_worker_id="postgres_lost_worker",
        lease_expires_at=datetime.utcnow() - timedelta(seconds=1),
    )
    first_recovery = postgres_sessions()
    second_recovery = postgres_sessions()
    try:
        assert services.recover_expired_runs(first_recovery) == 1
        # The first transaction owns the expired row until commit, so the
        # second worker skips it and cannot append a duplicate recovery event.
        assert services.recover_expired_runs(second_recovery) == 0
        second_recovery.commit()
        first_recovery.commit()
    finally:
        second_recovery.close()
        first_recovery.close()

    stale = _seed_run(
        postgres_sessions,
        suffix=f"{prefix}_stale",
        execution_status="running",
        claim_token="old-claim-token",
        claimed_by_worker_id="postgres_old_worker",
        lease_expires_at=datetime.utcnow() + timedelta(seconds=60),
    )
    stale_claim = services.ClaimedRun(
        run_id=stale.id,
        inbound_reply_id=stale.inbound_reply_id,
        claim_token="old-claim-token",
        worker_id="postgres_old_worker",
    )
    with postgres_sessions() as db:
        current = db.get(AgentFollowupRun, stale.id)
        assert current is not None
        current.execution_status = "failed"
        current.llm_status = "worker_lost"
        current.claim_token = None
        current.claimed_by_worker_id = None
        current.lease_expires_at = None
        db.commit()

    monkeypatch.setattr(services, "SessionLocal", postgres_sessions)
    assert services.process_claimed_run(stale_claim) is None

    tracked_run_ids = {first_queued.id, second_queued.id, only_queued.id, expired.id, stale.id}
    with postgres_sessions() as db:
        recovered = db.get(AgentFollowupRun, expired.id)
        stale_after = db.get(AgentFollowupRun, stale.id)
        assert recovered is not None and recovered.execution_status == "failed"
        assert recovered.llm_status == "worker_lost"
        assert stale_after is not None and stale_after.execution_status == "failed"
        assert stale_after.llm_status == "worker_lost"
        events = list(
            db.scalars(
                select(WorkerRunEvent)
                .where(WorkerRunEvent.agent_followup_run_id.in_(tracked_run_ids))
                .order_by(WorkerRunEvent.event_at.asc(), WorkerRunEvent.id.asc())
            ).all()
        )
        assert sum(event.event_type == "lease_expired_recovered" for event in events) == 1
        assert any(
            event.agent_followup_run_id == stale.id
            and event.event_type == "claim_result_discarded"
            and json.loads(event.metadata_json or "{}") == {"reason": "run_not_running"}
            for event in events
        )
        assert all("claim_token" not in (event.metadata_json or "") for event in events)
        assert db.scalar(select(func.count()).select_from(SimulatedOutboundInstruction)) == 0
