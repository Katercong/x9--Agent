from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False, suffix='.db').name}"

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from app.authorization import Capability, DepartmentMembership, Principal, Role, principal_from_memberships
from app.database import Base, SessionLocal, engine
from app.identity import ensure_capability
from app.main import app
from app.models import (
    AgentFollowupRun,
    AuthUser,
    AuthorizationAuditEvent,
    Creator,
    Department,
    DoNotContactConfirmation,
    HumanReviewDecision,
    InboundReply,
    SimulatedOutboundInstruction,
    UserDepartmentMembership,
)
from app.rbac_bootstrap import bootstrap_admin, main as bootstrap_main
from app.schemas import (
    AccessDepartmentPatchIn,
    AccessMembershipPatchIn,
    AccessUserPatchIn,
    DncConfirmationApproveIn,
    DncConfirmationRejectIn,
    DraftExportCreateIn,
    FailedReviewRetryIn,
    HumanReviewDecisionCreateIn,
)


@pytest.fixture(autouse=True)
def reset_rbac_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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


def test_dnc_and_retry_writes_require_reviewer_and_use_principal_for_audit(monkeypatch: pytest.MonkeyPatch):
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
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
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
        json={"code": " Creator Partnerships ", "name": "Creator Partnerships"},
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["department"]["code"] == "creator partnerships"
    assert response.json()["membership"]["role"] == "admin"
    assert response.json()["membership"]["auth_user_id"] == "auth_user_cross_admin"
    assert client.post(
        "/api/followup-agent/access/departments",
        json={"code": "creator partnerships", "name": "Duplicate"},
        headers=admin_headers,
    ).status_code == 409

    departments = client.get("/api/followup-agent/access/departments", headers=admin_headers)
    assert {department["code"] for department in departments.json()["items"]} == {
        "cross_border",
        "creator partnerships",
    }
    memberships = client.get(
        "/api/followup-agent/access/memberships?department_code=creator%20partnerships",
        headers=admin_headers,
    )
    assert memberships.status_code == 200
    assert len(memberships.json()["items"]) == 1

    disabled = client.patch(
        "/api/followup-agent/access/departments/creator%20partnerships",
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


def test_authorization_tables_compile_for_sqlite_and_postgresql_with_restrict_foreign_keys():
    tables = (AuthUser.__table__, Department.__table__, UserDepartmentMembership.__table__, AuthorizationAuditEvent.__table__)
    for table in tables:
        sqlite_sql = str(CreateTable(table).compile(dialect=sqlite.dialect()))
        postgresql_sql = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        assert "CREATE TABLE" in sqlite_sql
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


def test_rbac_foundation_migration_upgrades_and_downgrades_sqlite(tmp_path: Path):
    db_path = tmp_path / "rbac_migration.sqlite"
    database_url = f"sqlite:///{db_path.as_posix()}"
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
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"auth_users", "departments", "user_department_memberships", "authorization_audit_events"} <= tables
        foreign_keys = connection.execute("PRAGMA foreign_key_list(user_department_memberships)").fetchall()
        assert {row[6] for row in foreign_keys} == {"RESTRICT"}

    run_alembic("downgrade", "c4d5e6f7a8b9")
    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "auth_users" not in tables
        assert "authorization_audit_events" not in tables
