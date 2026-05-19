"""Tests for the v1.0.19 compatibility endpoints — proves the original
extension's payload shape lands creators in the right v3 queue."""
from __future__ import annotations

import json
from datetime import datetime

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.extension_run_progress import ExtensionRunProgress
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation


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


def test_x9_compat_contact_methods_and_canonical_source_show_in_feed(client):
    body = {
        "items": [{
            "handle": "x9_whatsapp_feed",
            "platform": "tiktok",
            "profile_url": "https://www.tiktok.com/@x9_whatsapp_feed",
            "display_name": "X9 WhatsApp Feed",
            "followers": "18.5K",
            "bio": "Business collab WhatsApp:+15551234567 IG @x9_whatsapp_feed",
            "source_video_url": "https://www.tiktok.com/@x9_whatsapp_feed/video/1",
            "notes": "keyword=pads_for_woman filter=qualified message=qualified",
            "last_seen_at": "2026-05-19 08:00:00",
        }],
    }
    r = client.post("/api/local/extension/x9-compat/ingest-creators", json=body)
    assert r.status_code == 200
    assert r.json()["items"][0]["action"] in {"inserted", "updated"}

    creators = client.get("/api/local/creators?source=x9_leads&handle_contains=x9_whatsapp_feed&limit=20").json()
    assert creators["total"] == 1
    assert creators["items"][0]["source"] == "x9_leads"

    feed = client.get("/api/local/collector/observations-feed?source=x9_leads&limit=100").json()
    row = next(it for it in feed["items"] if it["handle"] == "x9_whatsapp_feed")
    assert row["followers_raw"] == "18.5K"
    assert "whatsapp" in row["lead"]["contact_types"]
    assert "instagram" in row["lead"]["contact_types"]
    assert row["lead"]["source_video_url"].endswith("/video/1")


def test_x9_source_video_seed_is_not_persisted_or_counted(client):
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "source": "tiktok_creator_lead_browser_extension_1_0_19",
        "search_keyword": "pads for woman",
        "creator": {
            "handle": "seed_only_should_not_upload",
            "display_name": "seed_only_should_not_upload",
            "profile_url": "https://www.tiktok.com/@seed_only_should_not_upload",
        },
        "source_video": {
            "video_url": "https://www.tiktok.com/@seed_only_should_not_upload/video/1",
            "title": "video seed",
        },
        "lead_status": "source_video_seen",
    }
    db = SessionLocal()
    try:
        before = db.query(RawObservation).filter_by(platform="tiktok").count()
    finally:
        db.close()

    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    assert r.json()["action"] == "skipped"
    assert r.json()["reason"] == "source_video_seed_only"

    db = SessionLocal()
    try:
        after = db.query(RawObservation).filter_by(platform="tiktok").count()
        assert after == before
    finally:
        db.close()


def test_x9_profile_without_contact_is_not_persisted(client):
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "source": "tiktok_creator_lead_browser_extension_1_0_19",
        "search_keyword": "pads for woman",
        "creator": {
            "handle": "no_contact_should_drop",
            "display_name": "No Contact Should Drop",
            "profile_url": "https://www.tiktok.com/@no_contact_should_drop",
            "bio": "just videos, no contact methods here",
            "followers_raw": "12.3K",
            "followers_count": 12300,
            "email": None,
            "external_links": [],
        },
        "source_video": {
            "video_url": "https://www.tiktok.com/@no_contact_should_drop/video/1",
            "title": "profile reached",
        },
    }
    db = SessionLocal()
    try:
        before = db.query(RawObservation).filter_by(platform="tiktok").count()
    finally:
        db.close()

    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "skipped"
    assert body["reason"] == "missing_contact"
    assert body["observation_id"] is None

    db = SessionLocal()
    try:
        after = db.query(RawObservation).filter_by(platform="tiktok").count()
        assert after == before
        assert db.query(Creator).filter_by(handle="no_contact_should_drop").count() == 0
    finally:
        db.close()


def test_x9_profile_without_contact_is_not_persisted(client):
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "source": "tiktok_creator_lead_browser_extension_1_0_19",
        "search_keyword": "pads for woman",
        "creator": {
            "handle": "no_contact_should_drop",
            "display_name": "No Contact Should Drop",
            "profile_url": "https://www.tiktok.com/@no_contact_should_drop",
            "bio": "just videos, no contact methods here",
            "followers_raw": "12.3K",
            "followers_count": 12300,
            "email": None,
            "external_links": [],
        },
        "source_video": {
            "video_url": "https://www.tiktok.com/@no_contact_should_drop/video/1",
            "title": "profile reached",
        },
    }
    db = SessionLocal()
    try:
        before = db.query(RawObservation).filter_by(platform="tiktok").count()
    finally:
        db.close()

    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "skipped"
    assert body["reason"] == "missing_contact"
    assert body["observation_id"] is None

    db = SessionLocal()
    try:
        after = db.query(RawObservation).filter_by(platform="tiktok").count()
        assert after == before
        assert db.query(Creator).filter_by(handle="no_contact_should_drop").count() == 0
    finally:
        db.close()


def test_legacy_x9_source_video_seed_raw_is_hidden_from_feed_and_stats(client):
    before_total = client.get("/api/local/collector/source-stats").json()["sources"]["x9_leads"]["total"]
    raw_payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "source": "tiktok_creator_lead_browser_extension_1_0_19",
        "search_keyword": "pads for woman",
        "creator": {"handle": "legacy_seed_hidden", "display_name": "legacy_seed_hidden"},
        "source_video": {"video_url": "https://www.tiktok.com/@legacy_seed_hidden/video/1"},
        "lead_status": "source_video_seen",
    }
    db = SessionLocal()
    try:
        db.add(RawObservation(
            id="obs_legacy_seed_hidden",
            platform="tiktok",
            department_code="cross_border",
            source="tiktok_creator_lead_browser_extension_1_0_19",
            raw_json=json.dumps(raw_payload, separators=(",", ":")),
            content_hash="hash_legacy_seed_hidden",
            collected_at=datetime.now(),
        ))
        db.commit()
    finally:
        db.close()

    after_total = client.get("/api/local/collector/source-stats").json()["sources"]["x9_leads"]["total"]
    assert after_total == before_total
    feed = client.get("/api/local/collector/observations-feed?source=x9_leads&limit=100").json()
    assert all(item["handle"] != "legacy_seed_hidden" for item in feed["items"])


def test_x9_compat_ingest_updates_existing_creator_by_normalized_handle(client):
    db = SessionLocal()
    try:
        db.add(Creator(
            id="legacy_case_dup_creator",
            platform="TikTok",
            handle="CaseDup",
            display_name="Old Name",
            email="old@example.com",
            has_email=1,
            followers_count=100,
        ))
        db.commit()
    finally:
        db.close()

    body = {"items": [{
        "handle": " casedup ",
        "platform": "tiktok",
        "profile_url": "https://www.tiktok.com/@casedup",
        "display_name": "Latest Name",
        "followers": 2500,
        "email": "latest@example.com",
        "current_status": "prospect",
    }]}
    r = client.post("/api/local/extension/x9-compat/ingest-creators", json=body)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["action"] == "updated"
    assert item["creator_id"] == "legacy_case_dup_creator"

    db = SessionLocal()
    try:
        rows = [
            creator for creator in db.query(Creator).all()
            if (creator.platform or "").strip().lower() == "tiktok"
            and (creator.handle or "").strip().lstrip("@").lower() == "casedup"
        ]
        assert len(rows) == 1
        assert rows[0].display_name == "Latest Name"
        assert rows[0].email == "latest@example.com"
        assert rows[0].followers_count == 2500
    finally:
        db.close()


def test_x9_compat_no_contact_duplicate_is_skipped_without_overwriting_existing_creator(client):
    db = SessionLocal()
    try:
        db.add(Creator(
            id="legacy_no_contact_update",
            platform="tiktok",
            handle="duplicate_no_contact",
            display_name="Existing",
            email="kept@example.com",
            has_email=1,
        ))
        db.commit()
    finally:
        db.close()

    body = {"items": [{
        "handle": "duplicate_no_contact",
        "platform": "tiktok",
        "display_name": "Latest Existing",
        "current_status": "dropped",
        "notes": "keyword=test filter=no_email message=skipped",
    }]}
    r = client.post("/api/local/extension/x9-compat/ingest-creators", json=body)
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert item["action"] == "skipped"
    assert item["reason"] == "missing_contact"
    assert item["creator_id"] is None

    db = SessionLocal()
    try:
        saved = db.get(Creator, "legacy_no_contact_update")
        assert saved.display_name == "Existing"
        assert saved.current_status is None
        assert saved.email == "kept@example.com"
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
