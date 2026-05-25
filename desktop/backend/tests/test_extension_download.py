from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from desktop.backend.database import SessionLocal, init_db
from desktop.backend.main import app
from desktop.backend.services import auth_service


def _actor_config_from_zip(content: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        text = zf.read("x9_actor_config.js").decode("utf-8")
    prefix = "globalThis.X9_BUNDLED_ACTOR_CONFIG = "
    assert text.startswith(prefix)
    return json.loads(text[len(prefix):].strip().rstrip(";"))


def test_extension_download_is_public_zip():
    client = TestClient(app)
    response = client.get("/api/local/extension/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "x9_relay.js" in names
    config = _actor_config_from_zip(response.content)
    assert config["ok"] is False
    assert config["detail"] == "login_required"
    assert "testuser01" not in json.dumps(config)


def test_extension_download_embeds_current_user_actor_config():
    init_db()
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username="download_actor_user",
            password="X9@Test123",
            role="department_user",
            department_code="cross_border",
            display_name="Download Actor",
            is_active=True,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        token, _ = auth_service.create_session_for_user(db, user)
        user_id = user.id

    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    response = client.get("/api/local/extension/download")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert "Cookie" in response.headers["vary"]
    config = _actor_config_from_zip(response.content)
    assert config["ok"] is True
    assert config["source"] == "download_user"
    assert config["actor_user_id"] == user_id
    assert config["actor"]["username"] == "download_actor_user"
    assert config["actor"]["display_name"] == "Download Actor"
    assert config["actor_token"].startswith("v1.")
    assert "testuser01" not in json.dumps(config)


def test_actor_config_endpoint_returns_current_user_identity():
    init_db()
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username="portal_actor_user",
            password="X9@Test123",
            role="department_user",
            department_code="cross_border",
            display_name="Portal Actor",
            is_active=True,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        token, _ = auth_service.create_session_for_user(db, user)
        user_id = user.id

    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    response = client.get("/api/local/extension/actor-config")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["source"] == "portal_user"
    assert body["actor_user_id"] == user_id
    assert body["actor"]["username"] == "portal_actor_user"
