"""PostgreSQL constraints and one scoped terminal-review path."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.authorization import DepartmentMembership, Role, principal_from_memberships
from app.identity import get_current_principal
from app.main import app
from app.models import (
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    DeclineConfirmation,
    Department,
    FollowupTask,
    InboundReply,
    SimulatedOutboundInstruction,
    WorkerRunEvent,
)


pytestmark = pytest.mark.postgres_integration


def _seed_creator_reply(db: Session, *, creator_id: str, reply_id: str, department_code: str = "cross_border") -> None:
    db.add(Creator(id=creator_id, department_code=department_code, handle=creator_id))
    db.flush()
    db.add(
        InboundReply(
            id=reply_id,
            department_code=department_code,
            creator_id=creator_id,
            direction="inbound",
            channel="postgres_constraints",
            external_message_id=f"message-{reply_id}",
            body="Synthetic PostgreSQL test reply.",
            processing_status="need_ai_review",
        )
    )
    db.flush()


def test_postgresql_active_run_partial_unique_and_worker_event_restrict_foreign_key(
    postgres_sessions: sessionmaker[Session],
):
    """Production-only partial index and audit foreign-key semantics must execute, not just compile."""

    with postgres_sessions() as db:
        _seed_creator_reply(db, creator_id="pg_constraint_creator", reply_id="pg_constraint_reply")
        first = AgentFollowupRun(
            id="pg_constraint_run_first",
            department_code="cross_border",
            creator_id="pg_constraint_creator",
            inbound_reply_id="pg_constraint_reply",
            llm_status="not_configured",
            execution_status="queued",
        )
        db.add(first)
        db.commit()

        db.add(
            AgentFollowupRun(
                id="pg_constraint_run_duplicate",
                department_code="cross_border",
                creator_id="pg_constraint_creator",
                inbound_reply_id="pg_constraint_reply",
                llm_status="not_configured",
                execution_status="running",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        first = db.get(AgentFollowupRun, first.id)
        assert first is not None
        first.execution_status = "succeeded"
        db.commit()
        successor = AgentFollowupRun(
            id="pg_constraint_run_successor",
            department_code="cross_border",
            creator_id="pg_constraint_creator",
            inbound_reply_id="pg_constraint_reply",
            llm_status="not_configured",
            execution_status="queued",
        )
        db.add(successor)
        db.commit()
        db.add(
            WorkerRunEvent(
                id="pg_constraint_event",
                agent_followup_run_id=successor.id,
                department_code="cross_border",
                worker_id="pg_constraint_worker",
                event_type="claim_acquired",
            )
        )
        db.commit()

        db.delete(successor)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_postgresql_scoped_decline_confirmation_hides_foreign_reply_and_creates_no_outbound_work(
    postgres_sessions: sessionmaker[Session],
):
    """A reviewer can confirm only their department's decline; the terminal path never sends or queues AI."""

    with postgres_sessions() as db:
        db.add_all(
            [
                Department(id="pg_department_cross", code="cross_border", name="Cross Border"),
                Department(id="pg_department_foreign", code="foreign_trade", name="Foreign Trade"),
            ]
        )
        _seed_creator_reply(db, creator_id="pg_decline_creator", reply_id="pg_decline_reply")
        _seed_creator_reply(
            db,
            creator_id="pg_foreign_creator",
            reply_id="pg_foreign_reply",
            department_code="foreign_trade",
        )
        decline = db.get(InboundReply, "pg_decline_reply")
        assert decline is not None
        decline.reply_category = "not_interested"
        db.add(
            FollowupTask(
                id="pg_decline_open_task",
                department_code="cross_border",
                creator_id="pg_decline_creator",
                task_type="reply_followup_1",
                status="open",
            )
        )
        db.commit()

    principal = principal_from_memberships(
        user_id="pg_reviewer",
        identity_source="test",
        external_subject="pg_reviewer",
        display_name="PostgreSQL Reviewer",
        memberships=[DepartmentMembership("cross_border", Role.REVIEWER)],
    )
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        client = TestClient(app)
        assert client.get("/api/followup-agent/replies/pg_foreign_reply").status_code == 404
        confirmed = client.post("/api/followup-agent/review-items/pg_decline_reply/confirm-decline", json={})
        assert confirmed.status_code == 201, confirmed.text
        assert confirmed.json()["creator"]["current_status"] == "dropped"
        assert confirmed.json()["reply"]["processing_status"] == "reviewed"
        assert confirmed.json()["closed_followup_task_ids"] == ["pg_decline_open_task"]
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    with postgres_sessions() as db:
        confirmation = db.scalar(
            select(DeclineConfirmation).where(DeclineConfirmation.inbound_reply_id == "pg_decline_reply")
        )
        task = db.get(FollowupTask, "pg_decline_open_task")
        event = db.scalar(
            select(CreatorOutreachEvent).where(
                CreatorOutreachEvent.creator_id == "pg_decline_creator",
                CreatorOutreachEvent.event_type == "decline_confirmed_by_human",
            )
        )
        assert confirmation is not None and confirmation.actor_id == "pg_reviewer"
        assert task is not None and task.status == "closed_declined"
        assert event is not None
        assert db.scalar(select(func.count()).select_from(AgentFollowupRun)) == 0
        assert db.scalar(select(func.count()).select_from(SimulatedOutboundInstruction)) == 0
