from __future__ import annotations

import hashlib
import json
import threading
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
    Department,
    DoNotContactConfirmation,
    HumanReviewDecision,
    InboundReply,
    ManualDeliveryAccount,
    ManualDeliveryDailyQuota,
    ManualDeliveryEvent,
    ManualDeliveryRequest,
    SimulatedOutboundInstruction,
    UserDepartmentMembership,
)
from app.services import (
    MANUAL_DELIVERY_CONFIRMATION_TTL,
    MANUAL_DELIVERY_TRANSITIONS,
    block_manual_delivery_requests_for_creator,
    create_pending_manual_delivery_request,
    expire_due_deliveries,
    manual_delivery_quota_date,
    manual_delivery_snapshot_is_reliable,
    reserve_and_queue_manual_delivery_request,
    transition_manual_delivery_request,
)


@pytest.fixture
def client() -> TestClient:
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_principal, None)


def _set_test_principal(user_id: str, role: Role, *, department_code: str = "cross_border") -> None:
    app.dependency_overrides[get_current_principal] = lambda: principal_from_memberships(
        user_id=user_id,
        identity_source="test",
        external_subject=user_id,
        display_name=user_id,
        memberships=[DepartmentMembership(department_code, role)],
    )


def _provision_delivery_access(db, *, user_id: str, role: Role, department_code: str = "cross_border") -> AuthUser:
    department = db.scalar(select(Department).where(Department.code == department_code))
    if department is None:
        department = Department(
            id=f"department_outbox_{department_code}",
            code=department_code,
            name=department_code.replace("_", " ").title(),
        )
        db.add(department)
        db.flush()
    user = AuthUser(
        id=user_id,
        identity_source="test",
        external_subject=user_id,
        display_name=user_id,
    )
    db.add(user)
    db.flush()
    db.add(
        UserDepartmentMembership(
            id=f"membership_{user_id}_{department_code}",
            auth_user_id=user.id,
            department_id=department.id,
            role=role.value,
            is_active=True,
            authorization_source="test",
        )
    )
    db.commit()
    return user


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


def _create_account_via_api(client: TestClient, *, email: str = "reviewer@example.test") -> str:
    _set_test_principal("outbox_admin", Role.ADMIN)
    response = client.post(
        "/api/followup-agent/manual-delivery-accounts",
        json={
            "department_code": "cross_border",
            "owner_auth_user_id": "outbox_reviewer",
            "display_name": "Reviewer Workspace mailbox",
            "email": email,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["account"]["id"]


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
        event_count_before = db.scalar(
            select(func.count(ManualDeliveryEvent.id)).where(ManualDeliveryEvent.manual_delivery_request_id == request.id)
        )
        with pytest.raises(ValueError, match="reliable reply references"):
            transition_manual_delivery_request(
                db,
                request=request,
                target_status="queued",
                actor_id="outbox_reviewer",
            )
        db.flush()
        assert request.status == "pending_second_confirmation"
        assert db.scalar(
            select(func.count(ManualDeliveryEvent.id)).where(ManualDeliveryEvent.manual_delivery_request_id == request.id)
        ) == event_count_before
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


def test_account_directory_and_second_confirmation_queue_locally_without_gmail(client: TestClient):
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_admin", role=Role.ADMIN)
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        _creator, _reply, decision, request = _approved_decision(
            db,
            suffix="second-confirmation",
            metadata={
                "reply_to": "creator@example.test",
                "gmail_thread_id": "thread-second-confirmation",
                "rfc_message_id": "<second-confirmation@example.test>",
            },
        )
        decision_id = decision.id
        request_id = request.id

    account_id = _create_account_via_api(client)
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    mine = client.get("/api/followup-agent/manual-delivery-accounts/mine")
    assert mine.status_code == 200, mine.text
    assert [item["id"] for item in mine.json()["items"]] == [account_id]

    confirmed = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["message"] == "delivery was queued locally; no Gmail request was made"
    assert confirmed.json()["delivery"]["status"] == "queued"
    assert confirmed.json()["delivery"]["account"]["id"] == account_id
    assert "token" not in json.dumps(confirmed.json()).lower()
    detail = client.get(f"/api/followup-agent/review-decisions/{decision_id}/delivery-request")
    assert detail.status_code == 200, detail.text
    assert detail.json()["delivery"]["snapshot"]["draft_content"] == "Thanks for the reply. We will confirm the campaign details before responding."
    assert [event["event_type"] for event in detail.json()["events"]] == ["delivery_request_created", "delivery_queued"]

    duplicate = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    )
    assert duplicate.status_code == 409
    with SessionLocal() as db:
        request = db.get(ManualDeliveryRequest, request_id)
        assert request is not None
        assert request.status == "queued"
        assert request.quota_reserved is True
        quota = db.scalar(select(ManualDeliveryDailyQuota).where(ManualDeliveryDailyQuota.manual_delivery_account_id == account_id))
        assert quota is not None and quota.reserved_count == 1
        assert [event.event_type for event in db.scalars(
            select(ManualDeliveryEvent)
            .where(ManualDeliveryEvent.manual_delivery_request_id == request_id)
            .order_by(ManualDeliveryEvent.event_at.asc(), ManualDeliveryEvent.id.asc())
        ).all()] == ["delivery_request_created", "delivery_queued"]
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0


def test_second_confirmation_enforces_same_approver_account_owner_dnc_expiry_and_quota(client: TestClient):
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_admin", role=Role.ADMIN)
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        _provision_delivery_access(db, user_id="outbox_other_reviewer", role=Role.REVIEWER)
        _creator, _reply, decision, request = _approved_decision(
            db,
            suffix="confirmation-boundaries",
            metadata={"gmail_thread_id": "thread-boundaries", "rfc_message_id": "<boundaries@example.test>"},
        )
        decision_id = decision.id
        request_id = request.id

    owner_account_id = _create_account_via_api(client)
    _set_test_principal("outbox_other_reviewer", Role.REVIEWER)
    assert client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": owner_account_id},
    ).status_code == 403

    _set_test_principal("outbox_admin", Role.ADMIN)
    other_account = client.post(
        "/api/followup-agent/manual-delivery-accounts",
        json={
            "department_code": "cross_border",
            "owner_auth_user_id": "outbox_other_reviewer",
            "display_name": "Other reviewer mailbox",
            "email": "other-reviewer@example.test",
        },
    )
    assert other_account.status_code == 201, other_account.text
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    assert client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": other_account.json()["account"]["id"]},
    ).status_code == 403

    with SessionLocal() as db:
        request = db.get(ManualDeliveryRequest, request_id)
        creator = db.get(Creator, request.creator_id if request else "")
        assert request is not None and creator is not None
        creator.do_not_contact_status = "confirmed"
        db.commit()
    blocked = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": owner_account_id},
    )
    assert blocked.status_code == 409
    with SessionLocal() as db:
        request = db.get(ManualDeliveryRequest, request_id)
        assert request is not None and request.status == "blocked_by_dnc"
        assert request.quota_reserved is False
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0

        _creator, _reply, expired_decision, expired_request = _approved_decision(
            db,
            suffix="expired-confirmation",
            metadata={"gmail_thread_id": "thread-expired", "rfc_message_id": "<expired@example.test>"},
            now=datetime.utcnow() - MANUAL_DELIVERY_CONFIRMATION_TTL - timedelta(seconds=1),
        )
        expired_decision_id = expired_decision.id
        expired_request_id = expired_request.id
    expired = client.post(
        f"/api/followup-agent/review-decisions/{expired_decision_id}/delivery-confirmations",
        json={"delivery_account_id": owner_account_id},
    )
    assert expired.status_code == 409
    with SessionLocal() as db:
        expired_request = db.get(ManualDeliveryRequest, expired_request_id)
        assert expired_request is not None and expired_request.status == "expired"


def test_account_directory_rejects_operator_owners_allows_admin_deactivation_and_enforces_daily_limit(client: TestClient):
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_admin", role=Role.ADMIN)
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        _provision_delivery_access(db, user_id="outbox_operator", role=Role.OPERATOR)
        _creator, _reply, decision, _request = _approved_decision(
            db,
            suffix="quota-limit",
            metadata={"gmail_thread_id": "thread-quota", "rfc_message_id": "<quota@example.test>"},
        )
        decision_id = decision.id

    _set_test_principal("outbox_admin", Role.ADMIN)
    operator_owner = client.post(
        "/api/followup-agent/manual-delivery-accounts",
        json={
            "department_code": "cross_border",
            "owner_auth_user_id": "outbox_operator",
            "display_name": "Operator mailbox",
            "email": "operator@example.test",
        },
    )
    assert operator_owner.status_code == 409
    account_id = _create_account_via_api(client, email="quota-owner@example.test")

    with SessionLocal() as db:
        db.add(
            ManualDeliveryDailyQuota(
                id="quota_limit_full",
                manual_delivery_account_id=account_id,
                quota_date=manual_delivery_quota_date(datetime.utcnow()),
                reserved_count=40,
            )
        )
        db.commit()
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    full_quota = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    )
    assert full_quota.status_code == 409
    assert "daily limit" in full_quota.json()["detail"]

    assert client.post(
        f"/api/followup-agent/manual-delivery-accounts/{account_id}/deactivate",
        json={},
    ).status_code == 403
    _set_test_principal("outbox_admin", Role.ADMIN)
    deactivated = client.post(
        f"/api/followup-agent/manual-delivery-accounts/{account_id}/deactivate",
        json={},
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["account"]["is_active"] is False
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    assert client.get("/api/followup-agent/manual-delivery-accounts/mine").json()["items"] == []
    _set_test_principal("outbox_operator", Role.OPERATOR)
    assert client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    ).status_code == 403


def test_second_confirmation_rejects_missing_references_and_cross_department_access(client: TestClient):
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_admin", role=Role.ADMIN)
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        _creator, _reply, missing_decision, _request = _approved_decision(
            db,
            suffix="missing-reference-api",
            metadata={"reply_to": "creator@example.test"},
        )
        missing_decision_id = missing_decision.id
        _creator, _reply, scoped_decision, _request = _approved_decision(
            db,
            suffix="cross-department-api",
            metadata={"gmail_thread_id": "thread-cross", "rfc_message_id": "<cross@example.test>"},
        )
        scoped_decision_id = scoped_decision.id

    account_id = _create_account_via_api(client, email="missing-reference-owner@example.test")
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    missing_reference = client.post(
        f"/api/followup-agent/review-decisions/{missing_decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    )
    assert missing_reference.status_code == 409
    assert "reliable reply references" in missing_reference.json()["detail"]

    _set_test_principal("outbox_foreign_reviewer", Role.REVIEWER, department_code="other_department")
    cross_department = client.post(
        f"/api/followup-agent/review-decisions/{scoped_decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    )
    assert cross_department.status_code == 404


def test_dnc_confirmation_endpoint_blocks_queued_outbox_and_releases_reservation(client: TestClient):
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_admin", role=Role.ADMIN)
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        creator, _reply, decision, request = _approved_decision(
            db,
            suffix="dnc-route",
            metadata={"gmail_thread_id": "thread-dnc-route", "rfc_message_id": "<dnc-route@example.test>"},
        )
        decision_id = decision.id
        request_id = request.id
        creator_id = creator.id

    account_id = _create_account_via_api(client, email="dnc-route@example.test")
    _set_test_principal("outbox_reviewer", Role.REVIEWER)
    assert client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-confirmations",
        json={"delivery_account_id": account_id},
    ).status_code == 200

    with SessionLocal() as db:
        dnc_reply = InboundReply(
            id="reply_outbox_dnc_route",
            department_code="cross_border",
            creator_id=creator_id,
            channel="simulation",
            external_message_id="outbox-dnc-route-external",
            from_email="dnc@example.test",
            body="Please unsubscribe me.",
            processing_status="need_ai_review",
            reply_category="not_interested",
        )
        confirmation = DoNotContactConfirmation(
            id="dnc_outbox_route",
            department_code="cross_border",
            creator_id=creator_id,
            inbound_reply_id=dnc_reply.id,
            status="pending_confirmation",
            reason="explicit_opt_out",
        )
        creator_row = db.get(Creator, creator_id)
        assert creator_row is not None
        creator_row.do_not_contact_status = "pending_confirmation"
        db.add(dnc_reply)
        db.flush()
        db.add(confirmation)
        db.commit()

    approved = client.post("/api/followup-agent/dnc-confirmations/dnc_outbox_route/approve", json={})
    assert approved.status_code == 200, approved.text
    assert approved.json()["blocked_manual_delivery_request_ids"] == [request_id]
    with SessionLocal() as db:
        request = db.get(ManualDeliveryRequest, request_id)
        assert request is not None and request.status == "blocked_by_dnc"
        quota = db.scalar(select(ManualDeliveryDailyQuota).where(ManualDeliveryDailyQuota.manual_delivery_account_id == account_id))
        assert quota is not None and quota.reserved_count == 0
        events = db.scalars(
            select(ManualDeliveryEvent)
            .where(ManualDeliveryEvent.manual_delivery_request_id == request_id)
            .order_by(ManualDeliveryEvent.event_at.asc(), ManualDeliveryEvent.id.asc())
        ).all()
        assert events[-1].event_type == "delivery_blocked_by_dnc"
        assert db.scalar(select(func.count(SimulatedOutboundInstruction.id))) == 0
    detail = client.get(f"/api/followup-agent/review-decisions/{decision_id}/delivery-request")
    assert detail.status_code == 200, detail.text
    assert detail.json()["delivery"]["status"] == "blocked_by_dnc"
    assert detail.json()["delivery"]["snapshot"] is None


def test_concurrent_second_confirmation_reserves_only_one_queued_request():
    with SessionLocal() as db:
        _provision_delivery_access(db, user_id="outbox_reviewer", role=Role.REVIEWER)
        _creator, _reply, _decision, request = _approved_decision(
            db,
            suffix="concurrent-confirmation",
            metadata={"gmail_thread_id": "thread-concurrent", "rfc_message_id": "<concurrent@example.test>"},
        )
        account = ManualDeliveryAccount(
            id="account_outbox_concurrent",
            department_code="cross_border",
            owner_auth_user_id="outbox_reviewer",
            display_name="Concurrent mailbox",
            email="concurrent@example.test",
        )
        db.add(account)
        db.commit()
        request_id = request.id
        account_id = account.id

    first_has_locks = threading.Event()
    release_first = threading.Event()
    results: list[str] = []
    result_lock = threading.Lock()

    def confirm(*, wait_before_queue: bool) -> None:
        with SessionLocal() as db:
            delivery = db.scalar(select(ManualDeliveryRequest).where(ManualDeliveryRequest.id == request_id).with_for_update())
            account = db.scalar(select(ManualDeliveryAccount).where(ManualDeliveryAccount.id == account_id).with_for_update())
            assert delivery is not None and account is not None
            if wait_before_queue:
                first_has_locks.set()
                assert release_first.wait(timeout=10)
            try:
                reserve_and_queue_manual_delivery_request(
                    db,
                    request=delivery,
                    account=account,
                    actor_id="outbox_reviewer",
                )
                db.commit()
                outcome = "queued"
            except ValueError:
                db.rollback()
                outcome = "conflict"
            with result_lock:
                results.append(outcome)

    first = threading.Thread(target=confirm, kwargs={"wait_before_queue": True})
    second = threading.Thread(target=confirm, kwargs={"wait_before_queue": False})
    first.start()
    assert first_has_locks.wait(timeout=10)
    second.start()
    release_first.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    assert sorted(results) == ["conflict", "queued"]
    with SessionLocal() as db:
        request = db.get(ManualDeliveryRequest, request_id)
        assert request is not None and request.status == "queued"
        assert db.scalar(
            select(func.count(ManualDeliveryEvent.id)).where(ManualDeliveryEvent.manual_delivery_request_id == request_id)
        ) == 2
        quota = db.scalar(select(ManualDeliveryDailyQuota).where(ManualDeliveryDailyQuota.manual_delivery_account_id == account_id))
        assert quota is not None and quota.reserved_count == 1
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
