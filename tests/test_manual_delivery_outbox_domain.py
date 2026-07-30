from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DatabaseError

from app.authorization import DepartmentMembership, Role, principal_from_memberships
from app.database import SessionLocal
from app.identity import get_current_principal
from app.main import app
from app.models import (
    AgentFollowupRun,
    AuthUser,
    Creator,
    HumanReviewDecision,
    InboundReply,
    ManualDeliveryAccount,
    ManualDeliveryDailyQuota,
    ManualDeliveryEvent,
    ManualDeliveryRequest,
    SimulatedOutboundInstruction,
)
from app.services import (
    MANUAL_DELIVERY_CONFIRMATION_TTL,
    MANUAL_DELIVERY_TRANSITIONS,
    block_manual_delivery_requests_for_creator,
    create_pending_manual_delivery_request,
    expire_due_deliveries,
    manual_delivery_quota_date,
    manual_delivery_snapshot_is_reliable,
    transition_manual_delivery_request,
)


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_current_principal] = lambda: principal_from_memberships(
        user_id="outbox_reviewer",
        identity_source="test",
        external_subject="outbox-reviewer",
        display_name="Outbox Reviewer",
        memberships=[DepartmentMembership("cross_border", Role.REVIEWER)],
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_principal, None)


def _reviewable_rows(db, *, suffix: str, metadata: dict[str, object] | None = None) -> tuple[Creator, InboundReply, AgentFollowupRun]:
    creator = Creator(
        id=f"creator_outbox_{suffix}",
        department_code="cross_border",
        handle=f"outbox_{suffix}",
        email=f"{suffix}@creator.example",
        current_status="communicating",
    )
    reply = InboundReply(
        id=f"reply_outbox_{suffix}",
        department_code="cross_border",
        creator_id=creator.id,
        channel="simulation",
        external_message_id=f"outbox-external-{suffix}",
        from_email=f"{suffix}@creator.example",
        to_email="bd@example.test",
        subject="Campaign follow-up",
        body="Sounds interesting. Please send the campaign details.",
        processing_status="need_ai_review",
        reply_category="interested",
        metadata_json=json.dumps(metadata) if metadata is not None else None,
    )
    run = AgentFollowupRun(
        id=f"run_outbox_{suffix}",
        department_code="cross_border",
        creator_id=creator.id,
        inbound_reply_id=reply.id,
        reply_category="interested",
        llm_status="succeeded",
        execution_status="succeeded",
    )
    # No ORM relationships are declared for these legacy rows, so flush their
    # foreign-key parents before adding the dependent run.
    db.add_all((creator, reply))
    db.flush()
    db.add(run)
    db.commit()
    return creator, reply, run


def _approved_decision(
    db,
    *,
    suffix: str,
    metadata: dict[str, object] | None = None,
    now: datetime | None = None,
    dnc_blocked: bool = False,
):
    creator, reply, run = _reviewable_rows(db, suffix=suffix, metadata=metadata)
    if dnc_blocked:
        creator.do_not_contact_status = "confirmed"
        creator.do_not_contact_reason = "explicit_opt_out"
        db.commit()
    decision = HumanReviewDecision(
        id=f"decision_outbox_{suffix}",
        department_code="cross_border",
        creator_id=creator.id,
        inbound_reply_id=reply.id,
        agent_followup_run_id=run.id,
        outcome="approve_draft",
        final_draft="Thanks for the reply. We will confirm the campaign details before responding.",
        actor_id="outbox_reviewer",
        decided_at=now or datetime.utcnow(),
    )
    db.add(decision)
    db.flush()
    request = create_pending_manual_delivery_request(
        db,
        decision=decision,
        reply=reply,
        creator=creator,
        now=now,
    )
    db.commit()
    return creator, reply, decision, request


def _account_and_reservation(db, *, request: ManualDeliveryRequest, at: datetime) -> ManualDeliveryDailyQuota:
    owner = AuthUser(
        id=f"auth_outbox_{request.id}",
        identity_source="test",
        external_subject=f"outbox-{request.id}",
        display_name="Outbox Owner",
    )
    account = ManualDeliveryAccount(
        id=f"account_outbox_{request.id}",
        department_code=request.department_code,
        owner_auth_user_id=owner.id,
        display_name="Outbox Gmail",
        email=f"{request.id}@mail.example",
    )
    quota = ManualDeliveryDailyQuota(
        id=f"quota_outbox_{request.id}",
        manual_delivery_account_id=account.id,
        quota_date=manual_delivery_quota_date(at),
        reserved_count=1,
    )
    db.add_all((owner, account, quota))
    db.flush()
    request.manual_delivery_account_id = account.id
    request.account_email_snapshot = account.email
    request.account_owner_auth_user_id_snapshot = owner.id
    request.second_confirmed_by_auth_user_id = owner.id
    request.second_confirmed_at = at
    request.quota_reserved = True
    request.quota_reservation_date = quota.quota_date
    db.commit()
    return quota


def test_approved_draft_creates_one_immutable_pending_outbox_snapshot_and_no_outbound(client: TestClient):
    metadata = {
        "reply_to": "reply@example.creator",
        "gmail_thread_id": "thread-123",
        "rfc_message_id": "<message-123@example.creator>",
        "references": "<previous@example.creator> <message-123@example.creator>",
    }
    with SessionLocal() as db:
        _creator, reply, run = _reviewable_rows(db, suffix="approved", metadata=metadata)
        reply_id = reply.id
        run_id = run.id

    response = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run_id,
            "outcome": "approve_draft",
            "final_draft": "A human-edited and approved reply.",
        },
    )
    assert response.status_code == 201, response.text

    with SessionLocal() as db:
        request = db.scalar(select(ManualDeliveryRequest).where(ManualDeliveryRequest.inbound_reply_id == reply_id))
        assert request is not None
        assert request.status == "pending_second_confirmation"
        assert request.draft_content_snapshot == "A human-edited and approved reply."
        assert request.draft_sha256 == hashlib.sha256(request.draft_content_snapshot.encode("utf-8")).hexdigest()
        assert request.recipient_email_snapshot == "reply@example.creator"
        assert request.gmail_thread_id_snapshot == "thread-123"
        assert request.rfc_message_id_snapshot == "<message-123@example.creator>"
        assert manual_delivery_snapshot_is_reliable(request) is True
        assert request.expires_at - request.created_at <= MANUAL_DELIVERY_CONFIRMATION_TTL + timedelta(seconds=1)
        assert request.expires_at - request.created_at >= MANUAL_DELIVERY_CONFIRMATION_TTL - timedelta(seconds=1)
        assert db.scalar(select(func.count(ManualDeliveryEvent.id)).where(ManualDeliveryEvent.manual_delivery_request_id == request.id)) == 1
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0

        with pytest.raises(ValueError, match="snapshots are immutable"):
            request.subject_snapshot = "mutated subject"
            db.flush()
        db.rollback()


def test_missing_reliable_thread_reference_remains_pending_and_cannot_be_misrepresented_as_sendable():
    with SessionLocal() as db:
        _creator, _reply, _decision, request = _approved_decision(db, suffix="missing-reference", metadata={"reply_to": "creator@example.test"})
        assert request.status == "pending_second_confirmation"
        assert manual_delivery_snapshot_is_reliable(request) is False
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0


def test_dnc_at_approval_creates_a_blocked_outbox_audit_record_without_any_external_instruction():
    with SessionLocal() as db:
        _creator, _reply, _decision, request = _approved_decision(
            db,
            suffix="dnc-at-approval",
            metadata={"gmail_thread_id": "thread-dnc", "rfc_message_id": "<dnc@example.test>"},
            dnc_blocked=True,
        )
        assert request.status == "blocked_by_dnc"
        event = db.scalar(select(ManualDeliveryEvent).where(ManualDeliveryEvent.manual_delivery_request_id == request.id))
        assert event is not None
        assert event.event_type == "delivery_blocked_by_dnc"
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0


def test_delivery_state_machine_expiry_and_dnc_release_only_pre_send_quota():
    anchor = datetime(2026, 7, 30, 15, 0, 0)
    with SessionLocal() as db:
        creator, _reply, _decision, request = _approved_decision(
            db,
            suffix="expiry",
            metadata={
                "gmail_thread_id": "thread-expiry",
                "rfc_message_id": "<expiry@example.test>",
            },
            now=anchor,
        )
        expired_ids = expire_due_deliveries(db, now=anchor + MANUAL_DELIVERY_CONFIRMATION_TTL)
        db.commit()
        db.refresh(request)
        assert expired_ids == [request.id]
        assert request.status == "expired"
        assert request.quota_reserved is False

        with pytest.raises(ValueError, match="cannot transition"):
            transition_manual_delivery_request(
                db,
                request=request,
                target_status="sent",
                actor_id="outbox_reviewer",
            )

        _creator_2, _reply_2, _decision_2, dnc_request = _approved_decision(
            db,
            suffix="dnc",
            metadata={"gmail_thread_id": "thread-dnc", "rfc_message_id": "<dnc@example.test>"},
            now=anchor,
        )
        dnc_quota = _account_and_reservation(db, request=dnc_request, at=anchor)
        blocked_ids = block_manual_delivery_requests_for_creator(
            db,
            creator_id=dnc_request.creator_id,
            actor_id="outbox_reviewer",
            now=anchor + timedelta(minutes=2),
        )
        db.commit()
        db.refresh(dnc_request)
        db.refresh(dnc_quota)
        assert blocked_ids == [dnc_request.id]
        assert dnc_request.status == "blocked_by_dnc"
        assert dnc_request.quota_reserved is False
        assert dnc_quota.reserved_count == 0
        assert creator.id != dnc_request.creator_id


def test_delivery_state_graph_allows_only_explicit_lifecycle_transitions():
    assert MANUAL_DELIVERY_TRANSITIONS == {
        "pending_second_confirmation": frozenset({"queued", "expired", "blocked_by_dnc"}),
        "queued": frozenset({"sending", "blocked_by_dnc"}),
        "sending": frozenset({"sent", "failed", "unknown"}),
        "sent": frozenset(),
        "failed": frozenset(),
        "unknown": frozenset(),
        "expired": frozenset(),
        "blocked_by_dnc": frozenset(),
    }
    with SessionLocal() as db:
        _creator, _reply, _decision, request = _approved_decision(
            db,
            suffix="state-graph",
            metadata={"gmail_thread_id": "thread-graph", "rfc_message_id": "<graph@example.test>"},
        )
        transition_manual_delivery_request(db, request=request, target_status="queued", actor_id="outbox_reviewer")
        transition_manual_delivery_request(db, request=request, target_status="sending", actor_id="delivery-worker-not-started")
        transition_manual_delivery_request(db, request=request, target_status="sent", actor_id="delivery-worker-not-started")
        db.commit()
        db.refresh(request)
        assert request.status == "sent"


def test_manual_delivery_events_and_snapshots_are_immutable_in_postgresql():
    with SessionLocal() as db:
        _creator, _reply, _decision, request = _approved_decision(
            db,
            suffix="guards",
            metadata={"gmail_thread_id": "thread-guard", "rfc_message_id": "<guard@example.test>"},
        )
        event = db.scalar(select(ManualDeliveryEvent).where(ManualDeliveryEvent.manual_delivery_request_id == request.id))
        assert event is not None
        request_id = request.id
        event_id = event.id

    with SessionLocal() as db:
        with pytest.raises(DatabaseError, match="manual delivery request snapshots are immutable"):
            db.execute(
                text("UPDATE manual_delivery_requests SET subject_snapshot = 'tampered' WHERE id = :request_id"),
                {"request_id": request_id},
            )
            db.commit()
        db.rollback()
        with pytest.raises(DatabaseError, match="manual delivery events are immutable"):
            db.execute(
                text("UPDATE manual_delivery_events SET event_type = 'tampered' WHERE id = :event_id"),
                {"event_id": event_id},
            )
            db.commit()
        db.rollback()


def test_manual_delivery_outbox_migration_upgrades_and_downgrades_postgresql(temporary_postgres_database: str, run_alembic):
    assert run_alembic(temporary_postgres_database, "upgrade", "head").returncode == 0
    migration_engine = create_engine(temporary_postgres_database, future=True)
    try:
        with migration_engine.connect() as connection:
            tables = set(connection.dialect.get_table_names(connection))
            assert {
                "manual_delivery_accounts",
                "manual_delivery_daily_quotas",
                "manual_delivery_requests",
                "manual_delivery_events",
            }.issubset(tables)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "5e6f7a8b9c0d"
        assert run_alembic(temporary_postgres_database, "downgrade", "4d5e6f7a8b9c").returncode == 0
        with migration_engine.connect() as connection:
            tables = set(connection.dialect.get_table_names(connection))
            assert "manual_delivery_requests" not in tables
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "4d5e6f7a8b9c"
    finally:
        migration_engine.dispose()
