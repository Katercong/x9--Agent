from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TMP = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
TMP_YOUTUBE = tempfile.NamedTemporaryFile(delete=False, suffix=".youtube.db").name
os.environ["LOCAL_DB_URL"] = f"sqlite:///{TMP}"
os.environ["YOUTUBE_DB_URL"] = f"sqlite:///{TMP_YOUTUBE}"
os.environ["X9_ADMIN_EMAILS"] = "test-admin@example.com"

import pytest  # noqa: E402

from x9_creator_desktop_system.backend.database import init_db  # noqa: E402
from x9_creator_desktop_system.backend.database import SessionLocal  # noqa: E402
from x9_creator_desktop_system.backend.main import app  # noqa: E402
from x9_creator_desktop_system.backend.models.gmail_account import GmailAccount  # noqa: E402
from x9_creator_desktop_system.backend.services import auth_service  # noqa: E402
from x9_creator_desktop_system.backend.youtube_database import init_youtube_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap():
    init_db()
    init_youtube_db()
    yield
    try:
        os.unlink(TMP)
    except OSError:
        pass
    try:
        os.unlink(TMP_YOUTUBE)
    except OSError:
        pass


@pytest.fixture()
def client():
    with SessionLocal() as session:
        account = session.get(GmailAccount, "gmail_test_admin")
        if account is None:
            account = GmailAccount(
                id="gmail_test_admin",
                email="test-admin@example.com",
                display_name="Test Admin",
                token_json="{}",
                is_default=1,
                is_active=1,
            )
            session.add(account)
            session.commit()
        token, _user = auth_service.create_session_for_gmail_account(session, account)
    c = TestClient(app)
    c.cookies.set(auth_service.SESSION_COOKIE, token)
    return c
