from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.main import app
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.services import auth_service


def _upsert_creator(session, *, creator_id: str, department_code: str, current_status: str) -> None:
    row = session.get(Creator, creator_id)
    if row is None:
        row = Creator(
            id=creator_id,
            platform="tiktok",
            handle=creator_id,
        )
        session.add(row)
    row.department_code = department_code
    row.display_name = creator_id
    row.followers_count = 12_000
    row.email = f"{creator_id}@example.com"
    row.has_email = 1
    row.current_status = current_status
    row.recommendation_status = "recommended"
    row.recommended_product_type = "feminine_care"
    row.recommended_collab_type = "sample_collab"
    row.outreach_priority = "P1"
    row.owner_bd = "scope-test-bd"
    row.collected_at = datetime(2026, 5, 11, 8, 0, 0)


def _department_admin_client() -> TestClient:
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username="scope_department_admin",
            password="scope-pass-123",
            role="department_admin",
            department_code="cross_border",
            approval_status="active",
            is_active=True,
        )
        token, _ = auth_service.create_session_for_user(session, user, entry_scope="admin")
    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    return client


def test_business_dashboard_uses_admin_department_scope(client):
    marker = "业务看板范围测试"
    with SessionLocal() as session:
        _upsert_creator(
            session,
            creator_id="admin_scope_cross_border_creator",
            department_code="cross_border",
            current_status=marker,
        )
        _upsert_creator(
            session,
            creator_id="admin_scope_foreign_trade_creator",
            department_code="foreign_trade",
            current_status=marker,
        )
        session.commit()

    company_data = client.get("/api/local/admin/business-dashboard").json()
    assert company_data["scope"]["type"] == "company"
    company_status = {row["name"]: row["count"] for row in company_data["business_status"]}
    assert company_status[marker] == 2
    assert {row["code"] for row in company_data["departments"]} >= {"cross_border", "foreign_trade"}

    department_data = _department_admin_client().get("/api/local/admin/business-dashboard").json()
    assert department_data["scope"]["type"] == "department"
    assert department_data["scope"]["department_code"] == "cross_border"
    department_status = {row["name"]: row["count"] for row in department_data["business_status"]}
    assert department_status[marker] == 1
    assert {row["code"] for row in department_data["departments"]} == {"cross_border"}
