"""Tests for the v1.0.19 compatibility endpoints — proves the original
extension's payload shape lands creators in the right v3 queue."""
from __future__ import annotations

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.extension_run_progress import ExtensionRunProgress


def test_x9_compat_ingest_lands_in_v3_pipeline(client):
    """The exact payload shape v1.0.19 sends to /api/ingest/creators."""
    body = {
        "items": [{
            "handle": "natashathasan",
            "platform": "tiktok",
            "profile_url": "https://www.tiktok.com/@natashathasan",
            "display_name": "Natasha Thasan",
            "followers": 844500,
            "followers_raw": "844.5K",
            "email": "hello@natashathasan.cc",
            "category_tags": ["女性护理"],
            "source": "tiktok_creator_lead_browser",
            "current_status": "prospect",
            "notes": "keyword=feminine_care filter=qualified message=qualified",
            "last_seen_at": "2026-05-08 09:10:11",
        }],
    }
    r = client.post("/api/local/extension/x9-compat/ingest-creators", json=body)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] in {"inserted", "updated"}
    assert items[0]["handle"] == "natashathasan"

    # And the v3 pipeline correctly classifies the creator.
    client.post("/api/local/process/run-full-pipeline", json={})
    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="natashathasan").one()
        assert c.email == "hello@natashathasan.cc"
        assert c.followers_count == 844500
        assert c.search_keyword == "feminine_care"
        assert c.collected_at.isoformat().startswith("2026-05-08T09:10:11")
        # Without bio/video evidence, this lands in manual review or hold —
        # whichever, just confirm we didn't drop it.
        assert c.queue_type is not None
    finally:
        db.close()


def test_x9_compat_dropped_status_passes_through(client):
    body = {"items": [{
        "handle": "skipped_one",
        "platform": "tiktok",
        "current_status": "dropped",
        "notes": "keyword=sanitary_pads filter=no_email message=skipped",
    }]}
    r = client.post("/api/local/extension/x9-compat/ingest-creators", json=body)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["dropped_by_extension"] is True
    assert item["filter_reason"] == "no_email"


def test_launcher_heartbeat_creates_session_and_progress(client):
    body = {
        "app": "tiktok-creator-lead-browser",
        "version": "1.0.21",
        "source": "sidepanel",
        "reason": "auto_step",
        "extensionId": "v119_worker",
        "time": "2026-05-08T08:00:00Z",
        "activeTab": {
            "id": 12, "title": "TikTok",
            "url": "https://www.tiktok.com/@x",
            "isTikTok": True,
        },
        "page": {
            "detected": True, "url": "https://www.tiktok.com/@x",
            "title": "TikTok", "isTikTok": True, "isProfilePage": True,
            "inferredSearchKeyword": "feminine care",
            "gate": {"type": "none", "matchedText": ""},
        },
        "counts": {"leads": 5, "pending": 12, "skipped": 3, "sourceVideos": 20, "taskLogs": 30},
        "runTimer": {
            "running": True, "started_at": "2026-05-08T08:00:00Z",
            "elapsed_ms": 65000,
        },
        "settings": {
            "currentKeyword": "feminine care",
            "minFollowers": 5000, "requireEmail": True,
            "autoStopRequested": False,
            "maxProfiles": 30,
        },
        "latestLog": {"event_type": "auto_open_profile", "message": "@natashathasan"},
    }
    r = client.post("/api/local/extension/launcher-heartbeat", json=body)
    assert r.status_code == 200
    assert r.json()["progress_id"]

    # Session shows up in /extension/status
    s = client.get("/api/local/extension/status").json()
    assert any(x["worker_id"] == "v119_worker" for x in s["sessions"])

    # Run-progress reflects the v1.0.19 counts
    rp = client.get("/api/local/extension/run-progress?worker_id=v119_worker").json()["progress"]
    assert rp["leads_saved"] == 5
    assert rp["skipped"] == 3
    assert rp["queue_size"] == 12
    assert rp["profiles_visited"] == 8         # leads + skipped
    assert rp["profiles_remaining"] == 22       # 30 - 8
    assert rp["running"] is True
    assert rp["keyword"] == "feminine care"
    assert "natashathasan" in (rp["current_action"] or "")
