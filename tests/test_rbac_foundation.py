from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

from app.authorization import Capability, DepartmentMembership, Principal, Role, principal_from_memberships
from app.database import SessionLocal, get_db
from app import department_codes, department_codes_current, department_codes_v1
from app.demo_seed import DEMO_ACCESS_USERS, DEMO_DEPARTMENT, DEMO_REVIEWER_AUTH_USER_ID, seed_demo_data
from app.identity import ensure_capability, get_current_principal
from app.main import app
from app.models import (
    AgentFollowupRun,
    AuthUser,
    AuthorizationAuditEvent,
    Creator,
    CreatorOutreachEvent,
    DeclineConfirmation,
    Department,
    DoNotContactConfirmation,
    DraftExportRecord,
    FollowupTask,
    HumanReviewDecision,
    InboundReply,
    OutreachEmail,
    SimulatedOutboundInstruction,
    UserDepartmentMembership,
    WorkerRunEvent,
)
from app.rbac_bootstrap import bootstrap_admin, main as bootstrap_main
from app.schemas import (
    AccessDepartmentPatchIn,
    AccessMembershipPatchIn,
    AccessUserPatchIn,
    AccessDepartmentCreateIn,
    CreatorCreateIn,
    DncConfirmationApproveIn,
    DncConfirmationRejectIn,
    DraftExportCreateIn,
    FailedReviewRetryIn,
    HumanReviewDecisionCreateIn,
)


@contextmanager
def _migration_connection(database_url: str) -> Iterator[object]:
    """Expose text-query compatibility for PostgreSQL migration assertions."""

    migration_engine = create_engine(database_url, future=True)
    try:
        with migration_engine.connect() as connection:
            class ConnectionAdapter:
                def execute(self, statement: str):
                    return connection.execute(text(statement))

            yield ConnectionAdapter()
    finally:
        migration_engine.dispose()


@pytest.fixture(autouse=True)
def reset_rbac_database():
    yield


def _principal(role: Role) -> Principal:
    return principal_from_memberships(
        user_id="auth_user_test",
        identity_source="x9",
        external_subject="x9-subject-test",
        display_name="Test User",
        memberships=[DepartmentMembership("cross_border", role)],
    )


def _provision_access(
    *,
    identity_source: str = "x9",
    external_subject: str = "x9-reviewer",
    display_name: str = "Local Reviewer",
    user_active: bool = True,
    department_active: bool = True,
    membership_active: bool = True,
    role: Role = Role.REVIEWER,
) -> None:
    with SessionLocal() as db:
        user = AuthUser(
            id="auth_user_identity",
            identity_source=identity_source,
            external_subject=external_subject,
            display_name=display_name,
            is_active=user_active,
        )
        department = Department(
            id="department_identity",
            code="cross_border",
            name="Cross Border",
            is_active=department_active,
        )
        membership = UserDepartmentMembership(
            id="membership_identity",
            auth_user_id=user.id,
            department_id=department.id,
            role=role.value,
            is_active=membership_active,
            authorization_source="test",
        )
        db.add_all([user, department, membership])
        db.commit()


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed_x9_headers(
    *,
    secret: str = "test-hmac-secret",
    key_id: str = "test-key-1",
    subject_id: str = "x9-reviewer",
    issuer: str = "x9",
    audience: str = "x9-replychat-agent",
    issued_at: float | None = None,
    expires_at: float | None = None,
) -> dict[str, str]:
    issued_at = time.time() if issued_at is None else issued_at
    expires_at = issued_at + 60 if expires_at is None else expires_at
    assertion = json.dumps(
        {
            "issuer": issuer,
            "audience": audience,
            "subject_id": subject_id,
            "display_name": "Untrusted Assertion Name",
            "issued_at": issued_at,
            "expires_at": expires_at,
            "request_id": "request-test-1",
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), assertion, hashlib.sha256).digest()
    return {
        "X-X9-Identity": _base64url(assertion),
        "X-X9-Identity-Signature": _base64url(signature),
        "X-X9-Identity-Key-Id": key_id,
    }


def _configure_x9_assertion(monkeypatch: pytest.MonkeyPatch, *, keys: dict[str, str] | None = None) -> None:
    monkeypatch.setenv("RBAC_AUTH_MODE", "x9_assertion")
    monkeypatch.setenv("X9_IDENTITY_ISSUER", "x9")
    monkeypatch.setenv("X9_IDENTITY_AUDIENCE", "x9-replychat-agent")
    monkeypatch.setenv("X9_IDENTITY_HMAC_KEYS_JSON", json.dumps(keys or {"test-key-1": "test-hmac-secret"}))


def _provision_scoped_read_data() -> None:
    """Create two departments so HTTP tests exercise SQL-side scope filters."""

    with SessionLocal() as db:
        cross_reviewer = AuthUser(
            id="auth_user_cross_reviewer",
            identity_source="x9",
            external_subject="x9-cross-reviewer",
            display_name="Cross Reviewer",
        )
        cross_admin = AuthUser(
            id="auth_user_cross_admin",
            identity_source="x9",
            external_subject="x9-cross-admin",
            display_name="Cross Admin",
        )
        cross_operator = AuthUser(
            id="auth_user_cross_operator",
            identity_source="x9",
            external_subject="x9-cross-operator",
            display_name="Cross Operator",
        )
        foreign_member = AuthUser(
            id="auth_user_foreign_member",
            identity_source="x9",
            external_subject="x9-foreign-member",
            display_name="Foreign Member",
        )
        cross_department = Department(id="department_cross", code="cross_border", name="Cross Border")
        foreign_department = Department(id="department_foreign", code="foreign_trade", name="Foreign Trade")
        db.add_all(
            [
                cross_reviewer,
                cross_admin,
                cross_operator,
                foreign_member,
                cross_department,
                foreign_department,
                UserDepartmentMembership(
                    id="membership_cross_reviewer",
                    auth_user_id=cross_reviewer.id,
                    department_id=cross_department.id,
                    role=Role.REVIEWER.value,
                ),
                UserDepartmentMembership(
                    id="membership_cross_admin",
                    auth_user_id=cross_admin.id,
                    department_id=cross_department.id,
                    role=Role.ADMIN.value,
                ),
                UserDepartmentMembership(
                    id="membership_cross_operator",
                    auth_user_id=cross_operator.id,
                    department_id=cross_department.id,
                    role=Role.OPERATOR.value,
                ),
                UserDepartmentMembership(
                    id="membership_foreign_member",
                    auth_user_id=foreign_member.id,
                    department_id=foreign_department.id,
                    role=Role.REVIEWER.value,
                ),
            ]
        )
        db.flush()
        creators = [
            Creator(id="creator_cross", department_code="cross_border", handle="cross_creator"),
            Creator(id="creator_foreign", department_code="foreign_trade", handle="foreign_creator"),
        ]
        db.add_all(creators)
        db.flush()
        replies = [
            InboundReply(
                id="reply_cross_pending",
                department_code="cross_border",
                creator_id="creator_cross",
                direction="inbound",
                channel="simulation",
                external_message_id="scope-cross-pending",
                body="Cross-border pending review",
                processing_status="need_ai_review",
                reply_category="need_more_info",
                message_at=datetime.utcnow(),
            ),
            InboundReply(
                id="reply_foreign_pending",
                department_code="foreign_trade",
                creator_id="creator_foreign",
                direction="inbound",
                channel="simulation",
                external_message_id="scope-foreign-pending",
                body="Foreign-trade pending review",
                processing_status="need_ai_review",
                reply_category="need_more_info",
                message_at=datetime.utcnow(),
            ),
            InboundReply(
                id="reply_cross_decision",
                department_code="cross_border",
                creator_id="creator_cross",
                direction="inbound",
                channel="simulation",
                external_message_id="scope-cross-decision",
                body="Cross-border approved review",
                processing_status="reviewed",
                reply_category="need_more_info",
                message_at=datetime.utcnow(),
            ),
            InboundReply(
                id="reply_foreign_decision",
                department_code="foreign_trade",
                creator_id="creator_foreign",
                direction="inbound",
                channel="simulation",
                external_message_id="scope-foreign-decision",
                body="Foreign-trade approved review",
                processing_status="reviewed",
                reply_category="need_more_info",
                message_at=datetime.utcnow(),
            ),
        ]
        db.add_all(replies)
        db.flush()
        runs = [
            AgentFollowupRun(
                id="run_cross_pending",
                department_code="cross_border",
                creator_id="creator_cross",
                inbound_reply_id="reply_cross_pending",
                execution_status="succeeded",
                llm_status="succeeded",
            ),
            AgentFollowupRun(
                id="run_foreign_pending",
                department_code="foreign_trade",
                creator_id="creator_foreign",
                inbound_reply_id="reply_foreign_pending",
                execution_status="succeeded",
                llm_status="succeeded",
            ),
            AgentFollowupRun(
                id="run_cross_decision",
                department_code="cross_border",
                creator_id="creator_cross",
                inbound_reply_id="reply_cross_decision",
                execution_status="succeeded",
                llm_status="succeeded",
            ),
            AgentFollowupRun(
                id="run_foreign_decision",
                department_code="foreign_trade",
                creator_id="creator_foreign",
                inbound_reply_id="reply_foreign_decision",
                execution_status="succeeded",
                llm_status="succeeded",
            ),
        ]
        db.add_all(runs)
        db.flush()
        db.add_all(
            [
                WorkerRunEvent(
                    id="worker_event_cross_pending",
                    agent_followup_run_id="run_cross_pending",
                    department_code="cross_border",
                    worker_id="worker_cross_scope",
                    event_type="claim_acquired",
                    metadata_json='{"lease_seconds": 120}',
                ),
                WorkerRunEvent(
                    id="worker_event_foreign_pending",
                    agent_followup_run_id="run_foreign_pending",
                    department_code="foreign_trade",
                    worker_id="worker_foreign_scope",
                    event_type="claim_acquired",
                    metadata_json='{"lease_seconds": 120}',
                ),
                HumanReviewDecision(
                    id="decision_cross",
                    department_code="cross_border",
                    creator_id="creator_cross",
                    inbound_reply_id="reply_cross_decision",
                    agent_followup_run_id="run_cross_decision",
                    outcome="approve_draft",
                    final_draft="Cross approved draft",
                    actor_id="legacy_demo_operator",
                ),
                HumanReviewDecision(
                    id="decision_foreign",
                    department_code="foreign_trade",
                    creator_id="creator_foreign",
                    inbound_reply_id="reply_foreign_decision",
                    agent_followup_run_id="run_foreign_decision",
                    outcome="approve_draft",
                    final_draft="Foreign approved draft",
                    actor_id="legacy_demo_operator",
                ),
                SimulatedOutboundInstruction(
                    id="instruction_cross",
                    creator_id="creator_cross",
                    inbound_reply_id="reply_cross_pending",
                    action_type="simulation_only",
                    template_key="scope-test",
                    content="Cross instruction",
                ),
                SimulatedOutboundInstruction(
                    id="instruction_foreign",
                    creator_id="creator_foreign",
                    inbound_reply_id="reply_foreign_pending",
                    action_type="simulation_only",
                    template_key="scope-test",
                    content="Foreign instruction",
                ),
            ]
        )
        db.commit()


def test_role_capability_matrix_and_department_scope_are_explicit():
    operator = _principal(Role.OPERATOR)
    reviewer = _principal(Role.REVIEWER)
    admin = _principal(Role.ADMIN)

    assert operator.has_capability(Capability.REVIEW_READ, department_code="cross_border")
    assert operator.has_capability(Capability.DRAFT_EXPORT, department_code="cross_border")
    assert not operator.has_capability(Capability.REVIEW_DECIDE, department_code="cross_border")
    assert not operator.has_capability(Capability.DRAFT_EXPORT, department_code="foreign_trade")

    assert reviewer.has_capability(Capability.REVIEW_DECIDE, department_code="cross_border")
    assert reviewer.has_capability(Capability.DNC_DECIDE, department_code="cross_border")
    assert not reviewer.has_capability(Capability.ACCESS_MANAGE, department_code="cross_border")

    assert admin.has_capability(Capability.ACCESS_MANAGE, department_code="cross_border")
    assert admin.has_capability(Capability.CATALOG_MANAGE, department_code="cross_border")
    assert admin.allowed_departments_for(Capability.REVIEW_READ) == {"cross_border"}


def test_principal_rejects_empty_or_duplicate_department_memberships():
    with pytest.raises(ValueError, match="must not be empty"):
        DepartmentMembership("  ", Role.OPERATOR)

    with pytest.raises(ValueError, match="must not repeat"):
        principal_from_memberships(
            user_id="user",
            identity_source="x9",
            external_subject="subject",
            display_name=None,
            memberships=[
                DepartmentMembership("cross_border", Role.OPERATOR),
                DepartmentMembership("cross_border", Role.REVIEWER),
            ],
        )


def test_x9_signed_identity_resolves_local_principal_and_auth_me(monkeypatch: pytest.MonkeyPatch):
    _provision_access()
    _configure_x9_assertion(
        monkeypatch,
        keys={"test-key-1": "test-hmac-secret", "test-key-2": "rotated-test-secret"},
    )

    response = TestClient(app).get(
        "/api/followup-agent/auth/me",
        headers=_signed_x9_headers(secret="rotated-test-secret", key_id="test-key-2"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "auth_user_identity",
        "display_name": "Local Reviewer",
        "departments": [{"code": "cross_border", "role": "reviewer"}],
        "capabilities": [
            "catalog:read",
            "dnc:decide",
            "draft:export",
            "review:decide",
            "review:read",
            "run:enqueue",
            "run:retry",
        ],
    }


def test_x9_assertion_rejects_missing_expired_bad_signature_and_wrong_claims(monkeypatch: pytest.MonkeyPatch):
    _provision_access()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)

    assert client.get("/api/followup-agent/auth/me").status_code == 401

    expired = _signed_x9_headers(issued_at=time.time() - 200, expires_at=time.time() - 100)
    assert client.get("/api/followup-agent/auth/me", headers=expired).status_code == 401

    invalid_signature = _signed_x9_headers(secret="wrong-secret")
    assert client.get("/api/followup-agent/auth/me", headers=invalid_signature).status_code == 401

    wrong_issuer = _signed_x9_headers(issuer="another-system")
    assert client.get("/api/followup-agent/auth/me", headers=wrong_issuer).status_code == 401

    wrong_audience = _signed_x9_headers(audience="another-agent")
    assert client.get("/api/followup-agent/auth/me", headers=wrong_audience).status_code == 401

    wrong_key = _signed_x9_headers(key_id="unknown-key")
    assert client.get("/api/followup-agent/auth/me", headers=wrong_key).status_code == 401


@pytest.mark.parametrize(
    ("user_active", "department_active", "membership_active"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
def test_x9_assertion_requires_an_active_local_user_and_membership(
    monkeypatch: pytest.MonkeyPatch,
    user_active: bool,
    department_active: bool,
    membership_active: bool,
):
    _provision_access(
        user_active=user_active,
        department_active=department_active,
        membership_active=membership_active,
    )
    _configure_x9_assertion(monkeypatch)

    response = TestClient(app).get("/api/followup-agent/auth/me", headers=_signed_x9_headers())

    assert response.status_code == 403
    assert response.json()["detail"] == "no active ReplyChat access mapping"


def test_x9_assertion_rejects_unknown_local_user(monkeypatch: pytest.MonkeyPatch):
    _provision_access(external_subject="different-x9-user")
    _configure_x9_assertion(monkeypatch)

    response = TestClient(app).get("/api/followup-agent/auth/me", headers=_signed_x9_headers())

    assert response.status_code == 403


def test_demo_identity_is_explicit_and_never_enabled_outside_demo_or_test(monkeypatch: pytest.MonkeyPatch):
    _provision_access(identity_source="demo", external_subject="demo_reviewer", role=Role.OPERATOR)
    monkeypatch.setenv("RBAC_AUTH_MODE", "demo")
    monkeypatch.setenv("RBAC_DEMO_IDENTITY_SOURCE", "demo")
    monkeypatch.setenv("RBAC_DEMO_EXTERNAL_SUBJECT", "demo_reviewer")
    monkeypatch.setenv("APP_ENV", "production")

    production_response = TestClient(app).get("/api/followup-agent/auth/me")
    assert production_response.status_code == 503

    monkeypatch.setenv("APP_ENV", "demo")
    demo_response = TestClient(app).get("/api/followup-agent/auth/me")
    assert demo_response.status_code == 200
    assert demo_response.json()["display_name"] == "Local Reviewer"


def test_demo_seed_provisions_the_fictional_local_admin_for_the_demo_adapter(monkeypatch: pytest.MonkeyPatch):
    with SessionLocal() as db:
        assert seed_demo_data(db) > 0
        db.commit()
        assert db.get(AuthUser, DEMO_REVIEWER_AUTH_USER_ID) is not None
        assert db.scalar(select(Department).where(Department.code == DEMO_DEPARTMENT)) is not None
        memberships = db.scalars(select(UserDepartmentMembership)).all()
        assert {membership.role for membership in memberships} == {"operator", "reviewer", "admin"}
        assert db.scalar(select(func.count()).select_from(AuthorizationAuditEvent)) == len(DEMO_ACCESS_USERS)

    monkeypatch.setenv("RBAC_AUTH_MODE", "demo")
    monkeypatch.setenv("APP_ENV", "demo")
    monkeypatch.setenv("RBAC_DEMO_IDENTITY_SOURCE", "demo")
    monkeypatch.setenv("RBAC_DEMO_EXTERNAL_SUBJECT", "demo_reviewer")

    response = TestClient(app).get("/api/followup-agent/auth/me")

    assert response.status_code == 200
    assert response.json()["user_id"] == DEMO_REVIEWER_AUTH_USER_ID
    assert response.json()["departments"] == [{"code": DEMO_DEPARTMENT, "role": "reviewer"}]
    assert "review:decide" in response.json()["capabilities"]


def test_unconfigured_identity_and_capability_dependency_fail_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RBAC_AUTH_MODE", "unconfigured")
    monkeypatch.setenv("X9_IDENTITY_HMAC_KEYS_JSON", "{}")

    response = TestClient(app).get("/api/followup-agent/auth/me")

    assert response.status_code == 503
    with pytest.raises(HTTPException) as exc_info:
        ensure_capability(_principal(Role.OPERATOR), Capability.REVIEW_DECIDE, department_code="cross_border")
    assert exc_info.value.status_code == 403


def test_business_read_endpoints_require_a_principal(monkeypatch: pytest.MonkeyPatch):
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)

    for path in (
        "/api/followup-agent/reference-materials",
        "/api/followup-agent/outbound-instructions",
        "/api/followup-agent/replies/missing",
        "/api/followup-agent/runs/missing",
        "/api/followup-agent/runs",
        "/api/followup-agent/review-queue",
        "/api/followup-agent/review-items/missing",
        "/api/followup-agent/review-decisions/missing",
        "/api/followup-agent/review-decisions/missing/delivery-capability",
    ):
        assert client.get(path).status_code == 401


def test_business_write_endpoint_requires_a_principal(monkeypatch: pytest.MonkeyPatch):
    _configure_x9_assertion(monkeypatch)

    response = TestClient(app).post(
        "/api/followup-agent/creators",
        json={"id": "unauthenticated_creator", "department_code": "cross_border", "handle": "unauthenticated"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            HumanReviewDecisionCreateIn,
            {
                "agent_followup_run_id": "run",
                "outcome": "approve_draft",
                "final_draft": "Final draft",
                "actor_id": "forged",
            },
        ),
        (DncConfirmationApproveIn, {"actor_id": "forged"}),
        (DncConfirmationRejectIn, {"actor_id": "forged"}),
        (FailedReviewRetryIn, {"actor_id": "forged"}),
        (DraftExportCreateIn, {"actor_id": "forged"}),
    ],
)
def test_server_audited_write_schemas_reject_client_actor_id(model, payload):
    with pytest.raises(ValidationError, match="actor_id"):
        model.model_validate(payload)


def test_read_endpoints_filter_to_authorized_department_and_hide_cross_department_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    reviewer_headers = _signed_x9_headers(subject_id="x9-cross-reviewer")

    reference_response = client.get("/api/followup-agent/reference-materials", headers=reviewer_headers)
    assert reference_response.status_code == 200

    own_reply = client.get("/api/followup-agent/replies/reply_cross_pending", headers=reviewer_headers)
    assert own_reply.status_code == 200
    assert client.get("/api/followup-agent/replies/reply_foreign_pending", headers=reviewer_headers).status_code == 404

    own_run = client.get("/api/followup-agent/runs/run_cross_pending", headers=reviewer_headers)
    assert own_run.status_code == 200
    assert [
        (event["id"], event["department_code"], event["worker_id"], event["event_type"], event["metadata"])
        for event in own_run.json()["worker_events"]
    ] == [("worker_event_cross_pending", "cross_border", "worker_cross_scope", "claim_acquired", {"lease_seconds": 120})]
    assert client.get("/api/followup-agent/runs/run_foreign_pending", headers=reviewer_headers).status_code == 404

    runs_response = client.get("/api/followup-agent/runs", headers=reviewer_headers)
    assert runs_response.status_code == 200
    assert {item["id"] for item in runs_response.json()["items"]} == {"run_cross_pending", "run_cross_decision"}

    queue_response = client.get(
        "/api/followup-agent/review-queue?review_type=standard",
        headers=reviewer_headers,
    )
    assert queue_response.status_code == 200
    assert queue_response.json()["total"] == 1
    assert queue_response.json()["items"][0]["reply"]["id"] == "reply_cross_pending"
    assert client.get(
        "/api/followup-agent/review-queue?department_code=foreign_trade",
        headers=reviewer_headers,
    ).json()["total"] == 0

    assert client.get(
        "/api/followup-agent/review-items/reply_cross_pending",
        headers=reviewer_headers,
    ).status_code == 200
    assert client.get(
        "/api/followup-agent/review-items/reply_foreign_pending",
        headers=reviewer_headers,
    ).status_code == 404

    assert client.get(
        "/api/followup-agent/review-decisions/decision_cross",
        headers=reviewer_headers,
    ).status_code == 200
    assert client.get(
        "/api/followup-agent/review-decisions/decision_foreign",
        headers=reviewer_headers,
    ).status_code == 404
    assert client.get(
        "/api/followup-agent/review-decisions/decision_foreign/delivery-capability",
        headers=reviewer_headers,
    ).status_code == 404

    # Reviewer can read review data but not simulated instruction history.
    assert client.get("/api/followup-agent/outbound-instructions", headers=reviewer_headers).status_code == 403


def test_outbound_instruction_read_is_admin_only_and_still_department_scoped(monkeypatch: pytest.MonkeyPatch):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    response = TestClient(app).get("/api/followup-agent/outbound-instructions", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert [item["id"] for item in response.json()["items"]] == ["instruction_cross"]


def test_write_endpoints_enforce_role_department_scope_and_server_audit_subject(
    monkeypatch: pytest.MonkeyPatch,
):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    reviewer_headers = _signed_x9_headers(subject_id="x9-cross-reviewer")
    operator_headers = _signed_x9_headers(subject_id="x9-cross-operator")
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    product_body = {
        "id": "product_rbac_scope",
        "product_type": "rbac scope",
        "name": "RBAC Scope Product",
        "summary": "Only an admin may create this global catalog entry.",
    }
    assert client.post("/api/followup-agent/products", json=product_body, headers=operator_headers).status_code == 403
    assert client.post("/api/followup-agent/products", json=product_body, headers=admin_headers).status_code == 201

    assert client.post(
        "/api/followup-agent/creators",
        json={"id": "creator_reviewer_denied", "department_code": "cross_border", "handle": "denied"},
        headers=reviewer_headers,
    ).status_code == 403
    assert client.post(
        "/api/followup-agent/creators",
        json={"id": "creator_admin_allowed", "department_code": "cross_border", "handle": "allowed"},
        headers=admin_headers,
    ).status_code == 201
    assert client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_foreign", "body": "Do not expose another department.", "run_agent": False},
        headers=admin_headers,
    ).status_code == 404

    assert client.post(
        "/api/followup-agent/runs",
        json={"inbound_reply_id": "reply_foreign_pending"},
        headers=reviewer_headers,
    ).status_code == 404

    forged_actor = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": "run_cross_pending",
            "outcome": "approve_draft",
            "final_draft": "A locally reviewed draft.",
            "actor_id": "forged-browser-value",
        },
        headers=reviewer_headers,
    )
    assert forged_actor.status_code == 422

    decision_response = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": "run_cross_pending",
            "outcome": "approve_draft",
            "final_draft": "A locally reviewed draft.",
        },
        headers=reviewer_headers,
    )
    assert decision_response.status_code == 201
    decision_id = decision_response.json()["decision"]["id"]
    assert decision_response.json()["decision"]["actor_id"] == "auth_user_cross_reviewer"

    export_response = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/exports",
        json={},
        headers=operator_headers,
    )
    assert export_response.status_code == 201
    assert export_response.json()["export"]["actor_id"] == "auth_user_cross_operator"


def test_dnc_and_retry_writes_require_reviewer_and_use_principal_for_audit(
    monkeypatch: pytest.MonkeyPatch,
    clear_postgres_data,
):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    reviewer_headers = _signed_x9_headers(subject_id="x9-cross-reviewer")
    operator_headers = _signed_x9_headers(subject_id="x9-cross-operator")
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    dnc_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_cross", "body": "Please unsubscribe me.", "run_agent": False},
        headers=admin_headers,
    )
    assert dnc_reply.status_code == 200
    with SessionLocal() as db:
        confirmation_id = db.scalar(
            select(DoNotContactConfirmation.id).where(
                DoNotContactConfirmation.inbound_reply_id == dnc_reply.json()["reply"]["id"]
            )
        )
    assert confirmation_id is not None
    assert client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/approve",
        json={},
        headers=operator_headers,
    ).status_code == 403
    dnc_confirmation = client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/approve",
        json={},
        headers=reviewer_headers,
    )
    assert dnc_confirmation.status_code == 200
    assert dnc_confirmation.json()["confirmation"]["reviewed_by"] == "auth_user_cross_reviewer"

    # Rebuild a fresh scoped dataset for a non-terminal model-failure retry.
    clear_postgres_data()
    _provision_scoped_read_data()
    with SessionLocal() as db:
        failed_run = db.get(AgentFollowupRun, "run_cross_pending")
        assert failed_run is not None
        failed_run.execution_status = "failed"
        failed_run.llm_status = "validation_failed"
        failed_run.validation_error = "suggested_reply: Field required"
        db.commit()

    assert client.post(
        "/api/followup-agent/review-items/reply_cross_pending/retry",
        json={},
        headers=operator_headers,
    ).status_code == 403
    retry = client.post(
        "/api/followup-agent/review-items/reply_cross_pending/retry",
        json={},
        headers=reviewer_headers,
    )
    assert retry.status_code == 200
    assert retry.json()["run"]["created_by"] == "auth_user_cross_reviewer"


def test_decline_confirmation_requires_reviewer_scope_and_uses_principal_for_audit(
    monkeypatch: pytest.MonkeyPatch,
):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    reviewer_headers = _signed_x9_headers(subject_id="x9-cross-reviewer")
    operator_headers = _signed_x9_headers(subject_id="x9-cross-operator")
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    with SessionLocal() as db:
        cross_reply = InboundReply(
            id="reply_cross_decline",
            department_code="cross_border",
            creator_id="creator_cross",
            direction="inbound",
            channel="simulation",
            external_message_id="scope-cross-decline",
            body="No thanks, not interested.",
            processing_status="need_ai_review",
            reply_category="not_interested",
            message_at=datetime.utcnow(),
        )
        cross_admin_reply = InboundReply(
            id="reply_cross_admin_decline",
            department_code="cross_border",
            creator_id="creator_cross",
            direction="inbound",
            channel="simulation",
            external_message_id="scope-cross-admin-decline",
            body="No thanks, not interested again.",
            processing_status="need_ai_review",
            reply_category="not_interested",
            message_at=datetime.utcnow(),
        )
        foreign_reply = InboundReply(
            id="reply_foreign_decline",
            department_code="foreign_trade",
            creator_id="creator_foreign",
            direction="inbound",
            channel="simulation",
            external_message_id="scope-foreign-decline",
            body="No thanks, not interested.",
            processing_status="need_ai_review",
            reply_category="not_interested",
            message_at=datetime.utcnow(),
        )
        db.add_all([cross_reply, cross_admin_reply, foreign_reply])
        db.commit()

    assert client.post(
        "/api/followup-agent/review-items/reply_cross_decline/confirm-decline",
        json={},
        headers=operator_headers,
    ).status_code == 403
    assert client.post(
        "/api/followup-agent/review-items/reply_foreign_decline/confirm-decline",
        json={},
        headers=reviewer_headers,
    ).status_code == 404

    reviewer_confirmation = client.post(
        "/api/followup-agent/review-items/reply_cross_decline/confirm-decline",
        json={},
        headers=reviewer_headers,
    )
    assert reviewer_confirmation.status_code == 201
    assert reviewer_confirmation.json()["confirmation"]["actor_id"] == "auth_user_cross_reviewer"

    admin_confirmation = client.post(
        "/api/followup-agent/review-items/reply_cross_admin_decline/confirm-decline",
        json={},
        headers=admin_headers,
    )
    assert admin_confirmation.status_code == 201
    assert admin_confirmation.json()["confirmation"]["actor_id"] == "auth_user_cross_admin"

    with SessionLocal() as db:
        confirmations = {
            row.inbound_reply_id: row.actor_id
            for row in db.scalars(select(DeclineConfirmation)).all()
        }
        assert confirmations == {
            "reply_cross_decline": "auth_user_cross_reviewer",
            "reply_cross_admin_decline": "auth_user_cross_admin",
        }


def test_access_management_is_admin_only_scoped_audited_and_immediately_revocable(
    monkeypatch: pytest.MonkeyPatch,
):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")
    operator_headers = _signed_x9_headers(subject_id="x9-cross-operator")

    assert client.get("/api/followup-agent/access/departments", headers=operator_headers).status_code == 403
    departments = client.get("/api/followup-agent/access/departments", headers=admin_headers)
    assert departments.status_code == 200
    assert [department["code"] for department in departments.json()["items"]] == ["cross_border"]

    users = client.get("/api/followup-agent/access/users", headers=admin_headers)
    assert users.status_code == 200
    assert {user["id"] for user in users.json()["items"]} == {
        "auth_user_cross_admin",
        "auth_user_cross_operator",
        "auth_user_cross_reviewer",
    }
    assert client.patch(
        "/api/followup-agent/access/departments/foreign_trade",
        json={"name": "Hidden Foreign Trade"},
        headers=admin_headers,
    ).status_code == 404
    assert client.patch(
        "/api/followup-agent/access/users/auth_user_foreign_member",
        json={"is_active": False},
        headers=admin_headers,
    ).status_code == 404

    created_user = client.post(
        "/api/followup-agent/access/users",
        json={
            "identity_source": "X9",
            "external_subject": "x9-new-reviewer",
            "display_name": "New Reviewer",
        },
        headers=admin_headers,
    )
    assert created_user.status_code == 201
    user_id = created_user.json()["user"]["id"]
    assert created_user.json()["user"]["identity_source"] == "x9"
    assert client.post(
        "/api/followup-agent/access/users",
        json={"identity_source": "x9", "external_subject": "x9-new-reviewer"},
        headers=admin_headers,
    ).status_code == 409

    assert client.post(
        "/api/followup-agent/access/memberships",
        json={"auth_user_id": user_id, "department_code": "foreign_trade", "role": "reviewer"},
        headers=admin_headers,
    ).status_code == 404
    membership_response = client.post(
        "/api/followup-agent/access/memberships",
        json={"auth_user_id": user_id, "department_code": "cross_border", "role": "operator"},
        headers=admin_headers,
    )
    assert membership_response.status_code == 201
    membership_id = membership_response.json()["membership"]["id"]
    assert membership_response.json()["membership"]["granted_by_auth_user_id"] == "auth_user_cross_admin"

    new_user_headers = _signed_x9_headers(subject_id="x9-new-reviewer")
    initial_identity = client.get("/api/followup-agent/auth/me", headers=new_user_headers)
    assert initial_identity.status_code == 200
    assert initial_identity.json()["departments"] == [{"code": "cross_border", "role": "operator"}]

    promoted = client.patch(
        f"/api/followup-agent/access/memberships/{membership_id}",
        json={"role": "reviewer"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    assert promoted.json()["membership"]["role"] == "reviewer"
    assert "review:decide" in client.get("/api/followup-agent/auth/me", headers=new_user_headers).json()["capabilities"]

    revoked = client.patch(
        f"/api/followup-agent/access/memberships/{membership_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["membership"]["is_active"] is False
    assert client.get("/api/followup-agent/auth/me", headers=new_user_headers).status_code == 403

    audit_events = client.get("/api/followup-agent/access/audit-events", headers=admin_headers)
    assert audit_events.status_code == 200
    actions = {event["action"] for event in audit_events.json()["items"]}
    assert {"access_user_created", "access_membership_created", "access_membership_updated"} <= actions
    assert all(event["actor_auth_user_id"] == "auth_user_cross_admin" for event in audit_events.json()["items"])
    assert client.delete(f"/api/followup-agent/access/memberships/{membership_id}", headers=admin_headers).status_code == 405

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SimulatedOutboundInstruction)) == 2
        assert db.scalar(
            select(func.count()).select_from(AuthorizationAuditEvent).where(
                AuthorizationAuditEvent.target_auth_user_id == user_id
            )
        ) == 4


def test_access_department_creation_grants_scoped_admin_and_audits(monkeypatch: pytest.MonkeyPatch):
    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    response = client.post(
        "/api/followup-agent/access/departments",
        json={"code": "\tCreator-Partnerships\n", "name": "Creator Partnerships"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["department"]["code"] == "creator-partnerships"
    assert response.json()["membership"]["role"] == "admin"
    assert response.json()["membership"]["auth_user_id"] == "auth_user_cross_admin"
    assert client.post(
        "/api/followup-agent/access/departments",
        json={"code": "creator-partnerships", "name": "Duplicate"},
        headers=admin_headers,
    ).status_code == 409

    departments = client.get("/api/followup-agent/access/departments", headers=admin_headers)
    assert {department["code"] for department in departments.json()["items"]} == {
        "cross_border",
        "creator-partnerships",
    }
    memberships = client.get(
        "/api/followup-agent/access/memberships?department_code=creator-partnerships",
        headers=admin_headers,
    )
    assert memberships.status_code == 200
    assert len(memberships.json()["items"]) == 1

    disabled = client.patch(
        "/api/followup-agent/access/departments/creator-partnerships",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert disabled.status_code == 200
    assert disabled.json()["department"]["is_active"] is False
    audit = client.get("/api/followup-agent/access/audit-events", headers=admin_headers)
    assert {event["action"] for event in audit.json()["items"]} >= {
        "access_department_created",
        "access_department_updated",
        "access_membership_created",
    }


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AccessDepartmentCreateIn, {"code": "foreign trade", "name": "Foreign Trade"}),
        (AccessDepartmentCreateIn, {"code": "外贸", "name": "Foreign Trade"}),
        (CreatorCreateIn, {"id": "creator_invalid_department", "department_code": "ÄPFEL", "handle": "invalid"}),
    ],
)
def test_department_code_schemas_require_portable_ascii_slugs(model, payload):
    with pytest.raises(ValidationError, match="ASCII slug"):
        model.model_validate(payload)


def test_department_code_schema_canonicalizes_ascii_boundary_whitespace():
    assert AccessDepartmentCreateIn.model_validate(
        {"code": "\tFOREIGN_TRADE\n", "name": "Foreign Trade"}
    ).code == "foreign_trade"


def test_historical_department_code_migration_exports_are_frozen_v1():
    """Released revisions keep object identity with their explicitly frozen rule set."""

    assert department_codes.DEPARTMENT_CODE_BOUNDARY_WHITESPACE == department_codes_v1.DEPARTMENT_CODE_BOUNDARY_WHITESPACE
    assert department_codes.DEPARTMENT_CODE_SLUG is department_codes_v1.DEPARTMENT_CODE_SLUG
    assert department_codes.normalise_department_code is department_codes_v1.normalise_department_code
    assert department_codes.validate_department_code is department_codes_v1.validate_department_code
    assert department_codes.normalised_department_code_expression is department_codes_v1.normalised_department_code_expression
    assert department_codes_current.validate_department_code is not department_codes_v1.validate_department_code
    assert department_codes_current.normalised_postgresql_department_code_expression is not None


def test_access_department_creation_maps_concurrent_unique_conflict_to_409(monkeypatch: pytest.MonkeyPatch):
    """The database unique constraint is the final guard for a create race."""

    _provision_scoped_read_data()
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")
    original_flush = Session.flush

    def concurrent_department_insert_conflict(session: Session, *args, **kwargs):
        if any(
            isinstance(instance, Department) and instance.code == "race-department"
            for instance in session.new
        ):
            raise IntegrityError(
                "INSERT INTO departments",
                {"code": "race-department"},
                RuntimeError("duplicate department code"),
            )
        return original_flush(session, *args, **kwargs)

    monkeypatch.setattr(Session, "flush", concurrent_department_insert_conflict)

    response = client.post(
        "/api/followup-agent/access/departments",
        json={"code": " Race-Department ", "name": "Race Department"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "department code is already reserved"
    with SessionLocal() as db:
        assert db.scalar(select(Department.id).where(Department.code == "race-department")) is None
        assert db.scalar(select(func.count()).select_from(AuthorizationAuditEvent)) == 0


def test_access_department_cannot_claim_existing_business_department_code(monkeypatch: pytest.MonkeyPatch):
    """A missing catalog row must not let another department's admin claim legacy data."""

    _provision_access(external_subject="x9-cross-admin", role=Role.ADMIN)
    with SessionLocal() as db:
        legacy_creator = Creator(
            id="creator_legacy_foreign",
            department_code="foreign_trade",
            handle="legacy_foreign",
        )
        legacy_reply = InboundReply(
            id="reply_legacy_foreign",
            department_code="foreign_trade",
            creator_id=legacy_creator.id,
            direction="inbound",
            channel="simulation",
            external_message_id="legacy-foreign-reply",
            body="Legacy data must stay outside the cross-border admin scope.",
            processing_status="need_ai_review",
        )
        db.add_all([legacy_creator, legacy_reply])
        db.commit()

    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    response = client.post(
        "/api/followup-agent/access/departments",
        json={"code": " FOREIGN_TRADE ", "name": "Foreign Trade"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Department.id).where(Department.code == "foreign_trade")) is None
        assert db.get(InboundReply, "reply_legacy_foreign") is not None
    assert client.get(
        "/api/followup-agent/review-items/reply_legacy_foreign",
        headers=admin_headers,
    ).status_code == 404
    queue = client.get(
        "/api/followup-agent/review-queue?department_code=foreign_trade",
        headers=admin_headers,
    )
    assert queue.status_code == 200
    assert queue.json()["total"] == 0


def test_new_department_grants_its_creator_scope_for_new_business_data(monkeypatch: pytest.MonkeyPatch):
    _provision_access(external_subject="x9-cross-admin", role=Role.ADMIN)
    _configure_x9_assertion(monkeypatch)
    client = TestClient(app)
    admin_headers = _signed_x9_headers(subject_id="x9-cross-admin")

    created_department = client.post(
        "/api/followup-agent/access/departments",
        json={"code": " New-Operations ", "name": "New Operations"},
        headers=admin_headers,
    )
    assert created_department.status_code == 201
    assert created_department.json()["department"]["code"] == "new-operations"
    assert created_department.json()["membership"]["role"] == "admin"

    created_creator = client.post(
        "/api/followup-agent/creators",
        json={"id": "creator_new_operations", "department_code": " NEW-OPERATIONS ", "handle": "new_operations"},
        headers=admin_headers,
    )
    assert created_creator.status_code == 201
    with SessionLocal() as db:
        new_creator = db.get(Creator, "creator_new_operations")
        assert new_creator is not None
        assert new_creator.department_code == "new-operations"

    simulated_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_new_operations", "body": "Please share the campaign details.", "run_agent": False},
        headers=admin_headers,
    )
    assert simulated_reply.status_code == 200
    assert simulated_reply.json()["reply"]["department_code"] == "new-operations"


def test_creator_department_writes_require_an_active_catalog_entry():
    """Recheck catalog state after capability resolution to close revocation races."""

    with SessionLocal() as db:
        source_department = Department(id="department_source", code="source_department", name="Source")
        disabled_department = Department(
            id="department_disabled",
            code="disabled_department",
            name="Disabled",
            is_active=False,
        )
        creator = Creator(id="creator_catalog_source", department_code="source_department", handle="catalog_source")
        db.add_all([source_department, disabled_department, creator])
        db.commit()

    principal = principal_from_memberships(
        user_id="auth_user_race_test",
        identity_source="test",
        external_subject="race-test",
        display_name="Race Test Admin",
        memberships=[
            DepartmentMembership("source_department", Role.ADMIN),
            DepartmentMembership("missing_department", Role.ADMIN),
            DepartmentMembership("disabled_department", Role.ADMIN),
        ],
    )
    app.dependency_overrides[get_current_principal] = lambda: principal
    try:
        client = TestClient(app)
        assert client.post(
            "/api/followup-agent/creators",
            json={"id": "creator_missing_department", "department_code": "missing_department", "handle": "missing"},
        ).status_code == 409
        assert client.put(
            "/api/followup-agent/creators/creator_catalog_source",
            json={
                "department_code": "missing_department",
                "platform": "tiktok",
                "handle": "catalog_source",
                "display_name": None,
                "profile_url": None,
                "email": None,
                "bio": None,
                "followers_count": None,
                "owner_bd": None,
                "recommendation_reason": None,
                "recommended_product_type": None,
                "recommended_collab_type": None,
            },
        ).status_code == 409
        assert client.patch(
            "/api/followup-agent/creators/creator_catalog_source",
            json={"department_code": "disabled_department"},
        ).status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_principal, None)

    with SessionLocal() as db:
        assert db.get(Creator, "creator_missing_department") is None
        current_creator = db.get(Creator, "creator_catalog_source")
        assert current_creator is not None
        assert current_creator.department_code == "source_department"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AccessUserPatchIn, {}),
        (AccessMembershipPatchIn, {}),
        (AccessDepartmentPatchIn, {}),
        (AccessDepartmentPatchIn, {"name": None}),
    ],
)
def test_access_patch_schemas_require_an_explicit_valid_change(model, payload):
    with pytest.raises(ValidationError, match="at least one|must not be null"):
        model.model_validate(payload)


def test_authorization_models_enforce_unique_roles_and_restrict_deletes():
    with SessionLocal() as db:
        user = AuthUser(id="auth_user_unique", identity_source="x9", external_subject="subject_unique")
        department = Department(id="department_unique", code="department_unique", name="Unique Department")
        db.add_all([user, department])
        db.commit()

        db.add(AuthUser(id="auth_user_duplicate", identity_source="x9", external_subject="subject_unique"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        membership = UserDepartmentMembership(
            id="membership_unique",
            auth_user_id=user.id,
            department_id=department.id,
            role=Role.REVIEWER.value,
        )
        db.add(membership)
        db.commit()

        db.add(
            UserDepartmentMembership(
                id="membership_duplicate",
                auth_user_id=user.id,
                department_id=department.id,
                role=Role.OPERATOR.value,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            UserDepartmentMembership(
                id="membership_invalid_role",
                auth_user_id=user.id,
                department_id=department.id,
                role="unknown",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            AuthorizationAuditEvent(
                id="authorization_audit_unique",
                action="test_membership",
                target_auth_user_id=user.id,
                department_id=department.id,
            )
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(delete(AuthUser).where(AuthUser.id == user.id))
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(delete(Department).where(Department.id == department.id))
            db.commit()
        db.rollback()


def test_authorization_tables_compile_for_postgresql_with_restrict_foreign_keys():
    tables = (AuthUser.__table__, Department.__table__, UserDepartmentMembership.__table__, AuthorizationAuditEvent.__table__)
    for table in tables:
        postgresql_sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in postgresql_sql

    membership_postgresql_sql = str(CreateTable(UserDepartmentMembership.__table__).compile(dialect=postgresql.dialect()))
    audit_postgresql_sql = str(CreateTable(AuthorizationAuditEvent.__table__).compile(dialect=postgresql.dialect()))
    assert membership_postgresql_sql.count("ON DELETE RESTRICT") == 3
    assert audit_postgresql_sql.count("ON DELETE RESTRICT") == 3


def test_bootstrap_admin_is_explicit_idempotent_and_audited(capsys):
    with SessionLocal() as db:
        first = bootstrap_admin(
            db,
            identity_source="x9",
            external_subject="x9-first-admin",
            department_code="cross_border",
            department_name="Cross Border",
            display_name="First Admin",
        )
        db.commit()
        second = bootstrap_admin(
            db,
            identity_source="x9",
            external_subject="x9-first-admin",
            department_code="cross_border",
            department_name="Cross Border",
            display_name="First Admin",
        )
        db.commit()

        assert first[3] is True
        assert second[3] is False
        assert db.scalar(select(AuthUser).where(AuthUser.external_subject == "x9-first-admin")).is_active is True
        membership = db.scalar(select(UserDepartmentMembership).where(UserDepartmentMembership.id == first[2].id))
        assert membership is not None
        assert membership.role == Role.ADMIN.value
        assert db.scalar(select(AuthorizationAuditEvent).where(AuthorizationAuditEvent.action == "bootstrap_admin_membership"))
        assert len(db.scalars(select(AuthorizationAuditEvent)).all()) == 1

    with pytest.raises(SystemExit, match="--confirm"):
        bootstrap_main(
            [
                "--identity-source",
                "x9",
                "--external-subject",
                "x9-no-confirm",
                "--department-code",
                "cross_border",
            ]
        )

    assert bootstrap_main(
        [
            "--identity-source",
            "x9",
            "--external-subject",
            "x9-cli-admin",
            "--department-code",
            "foreign_trade",
            "--confirm",
        ]
    ) == 0
    assert '"department_code": "foreign_trade"' in capsys.readouterr().out


def test_rbac_foundation_migration_upgrades_and_downgrades_postgresql(temporary_postgres_database: str):
    database_url = temporary_postgres_database
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    def run_alembic(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_alembic("upgrade", "c4d5e6f7a8b9")
    run_alembic("upgrade", "head")
    with _migration_connection(database_url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
        assert {"auth_users", "departments", "user_department_memberships", "authorization_audit_events"} <= tables
        foreign_keys = connection.execute(
            "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
            "JOIN information_schema.table_constraints tc ON tc.constraint_name = rc.constraint_name "
            "WHERE tc.table_name = 'user_department_memberships'"
        ).fetchall()
        assert {row[0] for row in foreign_keys} == {"RESTRICT"}

    run_alembic("downgrade", "c4d5e6f7a8b9")
    with _migration_connection(database_url) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
        assert "auth_users" not in tables
        assert "authorization_audit_events" not in tables


def test_department_catalog_backfill_migration_preserves_business_scope_and_downgrade_data(
    monkeypatch: pytest.MonkeyPatch,
    temporary_postgres_database: str,
):
    """Catalog backfill and row normalization must keep historical data readable."""

    root = Path(__file__).resolve().parents[1]
    database_url = temporary_postgres_database
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    def run_alembic(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    run_alembic("upgrade", "d7e8f9a0b1c2")
    migration_engine = create_engine(database_url)
    MigrationSession = sessionmaker(bind=migration_engine, future=True)
    try:
        with MigrationSession() as db:
            creator = Creator(id="backfill_creator", department_code="\tDept_Creators\n", handle="backfill_creator")
            reply = InboundReply(
                id="backfill_reply",
                department_code="\tDEPT_REPLIES\n",
                creator_id=creator.id,
                direction="inbound",
                channel="simulation",
                external_message_id="backfill-reply",
                body="Backfill reply",
                processing_status="need_ai_review",
            )
            decision = HumanReviewDecision(
                id="backfill_decision",
                department_code="dept_decisions",
                creator_id=creator.id,
                inbound_reply_id=reply.id,
                agent_followup_run_id="backfill_run",
                outcome="close_without_draft",
                actor_id="backfill_actor",
            )
            db.add_all(
                [
                    creator,
                    reply,
                ]
            )
            db.flush()
            # This database deliberately stops at the historical RBAC head.
            # Insert the legacy run with the schema that existed then instead
            # of using the current ORM model, which now has newer columns.
            db.execute(
                text(
                    """
                    INSERT INTO agent_followup_runs
                        (id, department_code, creator_id, inbound_reply_id, llm_status, execution_status)
                    VALUES
                        ('backfill_run', :department_code, :creator_id, :inbound_reply_id, 'not_configured', 'succeeded')
                    """
                ),
                {
                    "department_code": "\tDEPT_RUNS\n",
                    "creator_id": creator.id,
                    "inbound_reply_id": reply.id,
                },
            )
            db.add_all(
                [
                    DoNotContactConfirmation(
                        id="backfill_dnc",
                        department_code="\tDept_Dnc\n",
                        creator_id=creator.id,
                        inbound_reply_id=reply.id,
                    ),
                    OutreachEmail(
                        id="backfill_outreach",
                        department_code="\tDEPT_OUTREACH\n",
                        creator_id=creator.id,
                    ),
                    CreatorOutreachEvent(
                        id="backfill_event",
                        department_code="\tdept_events\n",
                        creator_id=creator.id,
                        event_type="backfill",
                    ),
                    FollowupTask(
                        id="backfill_task",
                        department_code="\tdept_tasks\n",
                        creator_id=creator.id,
                        task_type="backfill",
                    ),
                    decision,
                ]
            )
            db.flush()
            db.add(
                DraftExportRecord(
                    id="backfill_export",
                    department_code="\tdept_exports\n",
                    human_review_decision_id=decision.id,
                    creator_id=creator.id,
                    inbound_reply_id=reply.id,
                    exported_content="Backfill export",
                    actor_id="backfill_actor",
                )
            )
            db.commit()
    finally:
        migration_engine.dispose()

    expected_codes = {
        "dept_creators",
        "dept_dnc",
        "dept_replies",
        "dept_outreach",
        "dept_events",
        "dept_tasks",
        "dept_runs",
        "dept_decisions",
        "dept_exports",
    }
    # The catalog backfill follows the same canonical convention, but the
    # original row-normalization revision only trimmed ordinary spaces.  Keep
    # the tab/newline row through that historical migration to reproduce the
    # strict-scope gap before the forward repair is applied.
    run_alembic("upgrade", "e8f9a0b1c2d3")
    with _migration_connection(database_url) as connection:
        catalog_codes = {row[0] for row in connection.execute("SELECT code FROM departments")}
        assert catalog_codes == expected_codes
        assert connection.execute(
            "SELECT department_code FROM inbound_replies WHERE id = 'backfill_reply'"
        ).fetchone()[0] == "\tDEPT_REPLIES\n"
        assert connection.execute("SELECT COUNT(*) FROM user_department_memberships").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM authorization_audit_events").fetchone()[0] == 0

    run_alembic("upgrade", "f9a0b1c2d3e4")
    with _migration_connection(database_url) as connection:
        assert connection.execute(
            "SELECT department_code FROM inbound_replies WHERE id = 'backfill_reply'"
        ).fetchone()[0] == "\tdept_replies\n"

    run_alembic("upgrade", "head")
    expected_codes_by_table = {
        "creators": "dept_creators",
        "do_not_contact_confirmations": "dept_dnc",
        "inbound_replies": "dept_replies",
        "outreach_emails": "dept_outreach",
        "creator_outreach_events": "dept_events",
        "followup_tasks": "dept_tasks",
        "agent_followup_runs": "dept_runs",
        "human_review_decisions": "dept_decisions",
        "draft_export_records": "dept_exports",
    }
    with _migration_connection(database_url) as connection:
        for table_name, expected_code in expected_codes_by_table.items():
            assert connection.execute(f"SELECT department_code FROM {table_name}").fetchone()[0] == expected_code

    access_engine = create_engine(database_url)
    AccessSession = sessionmaker(bind=access_engine, future=True)
    try:
        with AccessSession() as db:
            department = db.scalar(select(Department).where(Department.code == "dept_replies"))
            assert department is not None
            user = AuthUser(
                id="backfill_auth_admin",
                identity_source="x9",
                external_subject="x9-backfill-admin",
                display_name="Backfill Admin",
            )
            db.add_all(
                [
                    user,
                    UserDepartmentMembership(
                        id="backfill_membership_admin",
                        auth_user_id=user.id,
                        department_id=department.id,
                        role=Role.ADMIN.value,
                    ),
                ]
            )
            db.commit()

        def migrated_database() -> object:
            db = AccessSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = migrated_database
        _configure_x9_assertion(monkeypatch)
        client = TestClient(app)
        headers = _signed_x9_headers(subject_id="x9-backfill-admin")
        assert client.get("/api/followup-agent/review-items/backfill_reply", headers=headers).status_code == 200
        queue = client.get(
            "/api/followup-agent/review-queue?department_code=dept_replies",
            headers=headers,
        )
        assert queue.status_code == 200
        assert queue.json()["total"] == 1
        assert queue.json()["items"][0]["reply"]["id"] == "backfill_reply"
    finally:
        app.dependency_overrides.pop(get_db, None)
        access_engine.dispose()

    # This revision deliberately leaves backfilled catalog rows intact.  It is
    # therefore safe to migrate down one step without deleting later grants or
    # audit records, and an upgrade back to head remains idempotent.
    run_alembic("downgrade", "d7e8f9a0b1c2")
    with _migration_connection(database_url) as connection:
        assert {row[0] for row in connection.execute("SELECT code FROM departments")} == expected_codes
    run_alembic("upgrade", "head")
    with _migration_connection(database_url) as connection:
        assert {row[0] for row in connection.execute("SELECT code FROM departments")} == expected_codes


def test_department_code_boundary_whitespace_migration_rejects_idempotency_collision(
    temporary_postgres_database: str,
):
    """Tab/newline variants must be checked before a canonical scope rewrite."""

    root = Path(__file__).resolve().parents[1]
    database_url = temporary_postgres_database
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
        )

    result = run_alembic("upgrade", "d7e8f9a0b1c2")
    assert result.returncode == 0, result.stdout + result.stderr
    migration_engine = create_engine(database_url)
    MigrationSession = sessionmaker(bind=migration_engine, future=True)
    try:
        with MigrationSession() as db:
            first_creator = Creator(id="collision_creator_first", department_code="\tforeign_trade\n", handle="first")
            second_creator = Creator(id="collision_creator_second", department_code="\nforeign_trade\t", handle="second")
            db.add_all(
                [
                    first_creator,
                    second_creator,
                    InboundReply(
                        id="collision_reply_first",
                        department_code=first_creator.department_code,
                        creator_id=first_creator.id,
                        direction="inbound",
                        channel="simulation",
                        external_message_id="same-external-message",
                        body="first",
                        processing_status="need_ai_review",
                    ),
                    InboundReply(
                        id="collision_reply_second",
                        department_code=second_creator.department_code,
                        creator_id=second_creator.id,
                        direction="inbound",
                        channel="simulation",
                        external_message_id="same-external-message",
                        body="second",
                        processing_status="need_ai_review",
                    ),
                ]
            )
            db.commit()
    finally:
        migration_engine.dispose()

    result = run_alembic("upgrade", "head")

    assert result.returncode != 0
    assert "cannot normalize inbound_replies: idempotency key collision" in result.stdout + result.stderr
    with _migration_connection(database_url) as connection:
        # PostgreSQL upgrades are transactional: the collision rolls the
        # whole chained attempt back to the starting historical revision.
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "d7e8f9a0b1c2"
        assert connection.execute(
            "SELECT department_code FROM inbound_replies WHERE id = 'collision_reply_first'"
        ).fetchone()[0] == "\tforeign_trade\n"


def test_department_code_ascii_migration_rejects_non_ascii_historical_values(
    temporary_postgres_database: str,
):
    """Historical scope normalization must reject non-ASCII values deterministically."""

    root = Path(__file__).resolve().parents[1]
    database_url = temporary_postgres_database
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url

    def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
        )

    result = run_alembic("upgrade", "d7e8f9a0b1c2")
    assert result.returncode == 0, result.stdout + result.stderr
    migration_engine = create_engine(database_url)
    MigrationSession = sessionmaker(bind=migration_engine, future=True)
    try:
        with MigrationSession() as db:
            creator = Creator(id="non_ascii_creator", department_code="\tÄPFEL\n", handle="non_ascii")
            db.add_all(
                [
                    creator,
                    InboundReply(
                        id="non_ascii_reply",
                        department_code=creator.department_code,
                        creator_id=creator.id,
                        direction="inbound",
                        channel="simulation",
                        external_message_id="non-ascii-reply",
                        body="Non-ASCII legacy department code.",
                        processing_status="need_ai_review",
                    ),
                ]
            )
            db.commit()
    finally:
        migration_engine.dispose()

    result = run_alembic("upgrade", "head")

    assert result.returncode != 0
    assert "department code(s) are not valid ASCII slugs" in result.stdout + result.stderr
    with _migration_connection(database_url) as connection:
        # PostgreSQL upgrades are transactional, so the strict ASCII gate
        # leaves the legacy database at the starting revision.
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "d7e8f9a0b1c2"
        assert connection.execute(
            "SELECT department_code FROM inbound_replies WHERE id = 'non_ascii_reply'"
        ).fetchone()[0] == "\tÄPFEL\n"
