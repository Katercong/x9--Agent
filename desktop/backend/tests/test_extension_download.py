from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from x9_creator_desktop_system.backend.main import app


def test_extension_download_is_public_zip():
    client = TestClient(app)
    response = client.get("/api/local/extension/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "x9_relay.js" in names
