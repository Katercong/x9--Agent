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


def _ft_actor_config_from_zip(content: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        text = zf.read("extension/ft_actor.js").decode("utf-8")
        social_config = zf.read("extension/social/x9_actor_config.js").decode("utf-8")
    prefix = "globalThis.__X9_FT_ACTOR__ = "
    assert text.startswith(prefix)
    payload_text = text[len(prefix):].split(";\n", 1)[0]
    payload = json.loads(payload_text)
    assert "testuser01" not in social_config
    assert "cross_border" not in social_config
    return payload


def test_extension_download_is_public_zip():
    client = TestClient(app)
    response = client.get("/api/local/extension/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "x9_relay.js" in names
    assert "helper/install_ft_helper.ps1" not in names
    assert "README_安装说明.txt" not in names
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


def test_foreign_trade_extension_download_embeds_ft_actor_config():
    init_db()
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username="foreign_download_user",
            password="X9@Test123",
            role="department_user",
            department_code="foreign_trade",
            display_name="Foreign Download Actor",
            is_active=True,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        token, _ = auth_service.create_session_for_user(db, user)
        user_id = user.id

    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    response = client.get("/api/local/extension/download")

    assert response.status_code == 200
    assert "x9-foreign-trade-extension.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
        root_ft_actor = zf.read("ft_actor.js").decode("utf-8")
        douyin_runner = zf.read("extension/social/douyin_runner.js").decode("utf-8")
        douyin_content = zf.read("extension/social/douyin_content.js").decode("utf-8")
        douyin_panel = zf.read("extension/social/douyin_panel.js").decode("utf-8")
        xhs_runner = zf.read("extension/social/xhs_runner.js").decode("utf-8")
        xhs_panel = zf.read("extension/social/xhs_panel.js").decode("utf-8")
        social_sidepanel = zf.read("extension/social/sidepanel.html").decode("utf-8")
        recruit_sidepanel = zf.read("extension/recruit/sidepanel.js").decode("utf-8")
        install_script = zf.read("helper/install_ft_helper.ps1").decode("utf-8-sig")
        compat_script = zf.read("helper/install_companyleads.ps1").decode("utf-8-sig")
        readme = zf.read("README_安装说明.txt").decode("utf-8")
    assert "extension/manifest.json" in names
    assert "extension/ft_actor.js" in names
    assert "manifest.json" in names
    assert "ft_actor.js" in names
    assert "extension/social/sidepanel.html" in names
    assert "extension/social/douyin_content.js" in names
    assert "extension/social/xhs_content.js" in names
    assert "helper/native_host/companyleads_native_host.py" in names
    assert "helper/scraper/platform_contract.py" in names
    assert "helper/requirements.txt" in names
    assert "README_安装说明.txt" in names
    assert 'files: ["social/douyin_content.js"]' in douyin_runner
    assert 'files: ["social/xhs_content.js"]' in xhs_runner
    assert "collectProfileSearchResults" in douyin_content
    assert "collectProfileSearchCards" in douyin_content
    assert "当前页未识别到主页卡片，回退为视频作者/评论主页采集" in douyin_content
    assert 'boot(init);' in douyin_panel
    assert 'boot(init);' in xhs_panel
    assert '插件后台 5 秒内没有响应' in douyin_panel
    assert '插件后台 5 秒内没有响应' in xhs_panel
    assert 'id="autoScrollsInput"' in social_sidepanel
    assert 'id="autoMinDelayInput"' in social_sidepanel
    assert 'id="restEveryInput"' in social_sidepanel
    assert 'files: ["douyin_content.js"]' not in douyin_runner
    assert 'files: ["xhs_content.js"]' not in xhs_runner
    assert "CompanyLeads_local" not in recruit_sidepanel
    assert "foreign-trade-helper" in recruit_sidepanel
    assert "https://usx9.us" in install_script
    assert "install_ft_helper.ps1" in compat_script
    assert "helper/install_ft_helper.ps1" in readme
    config = _ft_actor_config_from_zip(response.content)
    assert config["department_code"] == "foreign_trade"
    assert root_ft_actor.startswith("globalThis.__X9_FT_ACTOR__ = ")
    assert config["actor_user_id"] == user_id
    assert config["actor"]["username"] == "foreign_download_user"
    assert config["actor_token"].startswith("v1.")


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
