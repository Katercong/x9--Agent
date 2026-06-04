from __future__ import annotations

from fastapi.testclient import TestClient

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend import main as backend_main
from x9_creator_desktop_system.backend.main import app
from x9_creator_desktop_system.backend.services import auth_service


def _client_for_role(username: str, role: str) -> TestClient:
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username=username,
            password="Preview@2026",
            role=role,
            department_code="cross_border",
            approval_status=auth_service.ACTIVE_STATUS,
            is_active=True,
        )
        entry_scope = "admin" if role in auth_service.ADMIN_ROLES else "workspace"
        token, _ = auth_service.create_session_for_user(session, user, entry_scope=entry_scope)
    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    return client


def test_department_user_cannot_enter_department_admin_spa() -> None:
    client = _client_for_role("route_member", "department_user")

    response = client.get("/d/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portal/"


def test_department_user_root_goes_to_portal() -> None:
    client = _client_for_role("route_member_root", "department_user")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portal/"


def test_legacy_workspace_goes_to_portal_home() -> None:
    client = _client_for_role("route_member_workspace", "department_user")

    response = client.get("/workspace/foreign-trade/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/portal/"


def test_missing_portal_build_does_not_loop_to_login(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(backend_main, "PORTAL_DIR", tmp_path / "missing-portal")

    response = backend_main.portal_index()

    assert response.status_code == 503
    assert "Portal frontend is not built" in response.body.decode("utf-8")


def test_super_admin_root_goes_to_workbench_dashboard() -> None:
    client = _client_for_role("route_super_admin_root", "super_admin")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/a/dashboard"


def test_super_admin_can_enter_email_auto_spa() -> None:
    client = _client_for_role("route_super_email_auto", "super_admin")

    response = client.get("/a/email-auto", follow_redirects=False)

    assert response.status_code == 200


def test_department_admin_can_enter_department_admin_spa() -> None:
    client = _client_for_role("route_department_admin", "department_admin")

    response = client.get("/d/dashboard", follow_redirects=False)

    assert response.status_code == 200


def test_department_admin_cannot_enter_email_auto_spa() -> None:
    client = _client_for_role("route_department_email_auto", "department_admin")

    response = client.get("/d/email-auto", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/d/dashboard"


def test_department_admin_cannot_call_email_auto_api() -> None:
    client = _client_for_role("route_department_email_auto_api", "department_admin")

    response = client.get("/api/local/email-auto/dashboard")

    assert response.status_code == 403


def test_department_admin_cannot_enter_member_portal() -> None:
    client = _client_for_role("route_department_admin_portal", "department_admin")

    response = client.get("/portal/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/d/dashboard"
