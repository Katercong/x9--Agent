"""Acceptance tests covering spec section 17."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
import pytest

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_migrate_idempotent(client):
    assert client.post("/api/local/db/migrate").status_code == 200
    assert client.post("/api/local/db/migrate").status_code == 200


def test_extension_heartbeat(client):
    r = client.post("/api/local/extension/heartbeat", json={
        "event_type": "extension_heartbeat",
        "extension_id": "x9_tiktok_collector",
        "extension_version": "3.0.0",
        "worker_id": "test_worker",
        "account_id": "test_account",
        "browser_profile": "chrome_default",
        "current_url": "https://www.tiktok.com/@example",
        "tiktok_page_status": "on_tiktok",
        "tiktok_login_status": "logged_in",
        "page_type": "creator_profile",
        "active_tab_title": "TikTok",
        "timestamp": "2026-05-08T00:00:00Z",
    })
    assert r.status_code == 200
    assert r.json()["status"] == "online"
    s = client.get("/api/local/extension/status").json()
    assert s["any_online"] is True


def test_observation_ingest(client):
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "search_keyword": "sanitary pads",
        "creator": {
            "handle": "test_handle", "display_name": "Test",
            "bio": "test", "followers_raw": "12.3K",
            "email": "test@gmail.com", "external_links": [],
            "store_assigned": "X9x9 Shop 01", "owner_bd": "Mercy",
        },
        "source_video": {"video_url": "https://www.tiktok.com/@x/video/1", "title": "t", "description": "d", "hashtags": []},
        "collected_at": "2026-05-08T00:00:00Z",
    }
    r1 = client.post("/api/local/collector/observations", json=payload)
    assert r1.json()["action"] == "inserted"
    assert r1.json()["pipeline"]["ok"] is True
    payload["collected_at"] = "2026-05-08 12:30:00"
    r2 = client.post("/api/local/collector/observations", json=payload)
    assert r2.json()["action"] == "updated"

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="test_handle").one()
        assert c.followers_count == 12300
    finally:
        db.close()

    listed = client.get("/api/local/creators?limit=50").json()["items"]
    saved = next(item for item in listed if item["handle"] == "test_handle")
    assert saved["collected_at"].startswith("2026-05-08T12:30:00")
    assert saved["store_assigned"] == "X9x9 Shop 01"
    assert saved["owner_bd"] == "Mercy"

    filtered = client.get("/api/local/creators?collected_date=2026-05-08&limit=50").json()["items"]
    assert any(item["handle"] == "test_handle" for item in filtered)


def test_contact_methods_from_creator_bio_filter(client):
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok",
        "search_keyword": "creator collab",
        "creator": {
            "handle": "whatsapp_creator",
            "display_name": "WhatsApp Creator",
            "bio": "Collabs via WhatsApp 15551234567 or IG @whatsapp_creator",
            "followers_raw": "18K",
            "email": None,
            "external_links": ["https://external.example/not-used-for-contact-filter"],
        },
        "source_video": {"video_url": "https://www.tiktok.com/@x/video/5", "title": "review", "description": "ugc"},
        "collected_at": "2026-05-08T10:00:00Z",
    }
    assert client.post("/api/local/collector/observations", json=payload).status_code == 200

    listed = client.get("/api/local/creators?contact_channel=whatsapp&limit=50").json()["items"]
    saved = next(item for item in listed if item["handle"] == "whatsapp_creator")
    assert saved["has_contact"] is True
    assert "whatsapp" in saved["contact_types"]
    assert "instagram" in saved["contact_types"]
    assert any(method["type"] == "whatsapp" for method in saved["contact_methods"])
    assert any(method["type"] == "instagram" and method["value"] == "@whatsapp_creator" for method in saved["contact_methods"])

    by_text = client.get("/api/local/creators?contact_contains=15551234567&limit=50").json()["items"]
    assert any(item["handle"] == "whatsapp_creator" for item in by_text)


def test_creator_table_import_csv_runs_pipeline(client):
    csv_body = (
        "handle,platform,display_name,bio,followers,email,whatsapp,instagram_handle,category_tags,source,current_status\n"
        "table_import_creator,tiktok,Table Import Creator,"
        "\"Period care UGC creator\",25000,,15551234567,@table_import_ig,"
        "\"[\"\"feminine_care\"\", \"\"ugc\"\"]\",table_test,已寄样。\n"
    ).encode("utf-8")
    r = client.post(
        "/api/local/import/creators/table?filename=creators.csv",
        content=csv_body,
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["inserted"] == 1
    assert data["failed"] == 0
    assert data["items"][0]["pipeline"]["ok"] is True

    listed = client.get("/api/local/creators?handle_contains=table_import_creator&limit=5").json()["items"]
    saved = next(item for item in listed if item["handle"] == "table_import_creator")
    assert saved["recommendation_status"] is not None
    assert saved["current_status"] == "已寄样"
    assert "whatsapp" in saved["contact_types"]
    assert "instagram" in saved["contact_types"]

    by_status = client.get("/api/local/creators?current_status=已寄样&limit=50").json()["items"]
    assert any(item["handle"] == "table_import_creator" for item in by_status)


def test_search_keyword_only_match(client):
    client.post("/api/local/collector/observations", json={
        "event_type": "creator_observation",
        "platform": "tiktok",
        "search_keyword": "sanitary pads",
        "creator": {"handle": "search_only_creator", "bio": "just vibing in NYC",
                    "followers_raw": "30K", "email": "hi@gmail.com", "display_name": "x"},
        "source_video": {"video_url": "https://www.tiktok.com/@x", "title": "TikTok - Make Your Day", "description": None},
    })
    client.post("/api/local/process/run-full-pipeline", json={})
    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="search_only_creator").one()
        assert "search_keyword_only_match" in (c.risk_tags_json or "")
        assert "manual_review_required" not in (c.risk_tags_json or "")
        assert c.queue_type == "low_confidence_hold"
        assert c.review_required == 0
        assert c.recommendation_status == "hold"
    finally:
        db.close()


def test_recommendation_queues(client):
    samples = [
        # Strong feminine -> conversion queue
        ("fem_strong", "menstrual care reviews and period products. business: hi@me.co",
         "60K", "hi@me.co", "feminine care",
         "https://www.tiktok.com/@x/video/1", "my period routine", "panty liner reviews"),
        # Medium feminine, good DQ -> warm lead
        ("fem_medium", "skincare and self care lifestyle, occasional period care picks",
         "120K", "team@selfcare.com", "feminine care",
         "https://www.tiktok.com/@x/video/2", "morning routine", "self care wellness"),
        # Macro low fit -> brand awareness
        ("macro_low", "comedy creator since 2018", "5M", "agent@bigtalent.com", "vintage",
         "https://www.tiktok.com/@x/video/3", "skit time", "lol"),
        # No email -> no_contact_info_queue
        ("no_email_creator", "mom life and home routine", "20K", None, "lifestyle",
         "https://www.tiktok.com/@x/video/4", "morning routine for moms", "home cleaning"),
    ]
    for handle, bio, fol, email, kw, video, title, desc in samples:
        client.post("/api/local/collector/observations", json={
            "event_type": "creator_observation",
            "platform": "tiktok",
            "search_keyword": kw,
            "creator": {"handle": handle, "bio": bio, "followers_raw": fol,
                        "email": email, "display_name": handle, "external_links": []},
            "source_video": {"video_url": video, "title": title, "description": desc, "hashtags": []},
        })
    client.post("/api/local/process/run-full-pipeline", json={})

    expected = {
        "fem_strong": "feminine_conversion_queue",
        "fem_medium": "feminine_warm_lead_queue",
        "macro_low": "macro_brand_awareness_queue",
        "no_email_creator": "no_contact_info_queue",
    }
    db = SessionLocal()
    try:
        for handle, queue in expected.items():
            c = db.query(Creator).filter_by(handle=handle).one()
            assert c.queue_type == queue, f"@{handle}: got {c.queue_type}, expected {queue}"
    finally:
        db.close()


def test_creator_list_sorting(client):
    now = datetime(2026, 5, 8, 12, 0, 0)
    rows = [
        Creator(
            id="sort_case_big",
            platform="tiktok",
            handle="sort_case_big",
            followers_count=900_000,
            email="big@example.com",
            has_email=1,
            outreach_priority="P3",
            recommendation_score=40,
            primary_product_fit_score=35,
            recommendation_status="recommended",
            current_status="待建联",
            collected_at=now - timedelta(days=2),
        ),
        Creator(
            id="sort_case_strong",
            platform="tiktok",
            handle="sort_case_strong",
            followers_count=40_000,
            email="strong@example.com",
            has_email=1,
            outreach_priority="P2",
            recommendation_score=96,
            primary_product_fit_score=92,
            recommendation_status="recommended",
            current_status="待回复",
            collected_at=now - timedelta(days=1),
        ),
        Creator(
            id="sort_case_published",
            platform="tiktok",
            handle="sort_case_published",
            followers_count=80_000,
            email="published@example.com",
            has_email=1,
            outreach_priority="P4",
            recommendation_score=50,
            primary_product_fit_score=45,
            recommendation_status="recommended",
            current_status="视频已发布",
            collected_at=now - timedelta(hours=12),
        ),
        Creator(
            id="sort_case_urgent",
            platform="tiktok",
            handle="sort_case_urgent",
            followers_count=120_000,
            email=None,
            has_email=0,
            outreach_priority="P1",
            recommendation_score=70,
            primary_product_fit_score=65,
            recommendation_status="recommended",
            current_status="已寄样",
            collected_at=now,
        ),
    ]
    db = SessionLocal()
    try:
        for row in rows:
            db.merge(row)
        db.commit()
    finally:
        db.close()

    by_followers = client.get("/api/local/creators?handle_contains=sort_case_&sort_by=followers&limit=10").json()["items"]
    assert by_followers[0]["handle"] == "sort_case_big"

    by_score = client.get("/api/local/creators?handle_contains=sort_case_&sort_by=score&limit=10").json()["items"]
    assert by_score[0]["handle"] == "sort_case_strong"

    by_priority = client.get("/api/local/creators?handle_contains=sort_case_&sort_by=priority&limit=10").json()["items"]
    assert by_priority[0]["handle"] == "sort_case_urgent"

    by_contact = client.get("/api/local/creators?handle_contains=sort_case_&sort_by=contactable&limit=10").json()["items"]
    assert by_contact[0]["has_email"] is True

    follower_window = client.get("/api/local/creators?handle_contains=sort_case_&min_followers=100000&max_followers=200000&limit=10").json()["items"]
    assert [item["handle"] for item in follower_window] == ["sort_case_urgent"]

    current_status = client.get("/api/local/creators?handle_contains=sort_case_&current_status=视频已发布&limit=10").json()["items"]
    assert [item["handle"] for item in current_status] == ["sort_case_published"]

    reply_status = client.get("/api/local/creators?handle_contains=sort_case_&current_status=待回复&limit=10").json()["items"]
    assert [item["handle"] for item in reply_status] == ["sort_case_strong"]

    pending_status = client.get("/api/local/creators?handle_contains=sort_case_&current_status=待建联&limit=10").json()["items"]
    assert [item["handle"] for item in pending_status] == ["sort_case_big"]

    assert client.get("/api/local/creators?sort_by=unknown").status_code == 400


def test_no_manual_review_task_created_for_search_only_hold(client):
    client.post("/api/local/collector/observations", json={
        "event_type": "creator_observation",
        "platform": "tiktok",
        "search_keyword": "sanitary pads",
        "creator": {"handle": "no_review_task_creator", "bio": "daily life",
                    "followers_raw": "25K", "email": "hello@gmail.com", "display_name": "x"},
        "source_video": {"video_url": "https://www.tiktok.com/@x", "title": "TikTok - Make Your Day", "description": None},
    })
    client.post("/api/local/process/run-full-pipeline", json={})
    tasks = client.get("/api/local/review-tasks?status=pending").json()
    assert not any(item["creator_id"].endswith("no_review_task_creator") for item in tasks["items"])


def test_export_csv(client):
    r = client.get("/api/local/export/recommended-creators.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(body))
    expected = {
        "handle", "display_name", "profile_url", "followers_count", "email",
        "contact_types", "contact_methods",
        "recommended_product_type", "recommended_collab_type", "outreach_priority",
        "current_status", "recommendation_status", "recommendation_reason", "risk_tags",
        "next_action", "notes",
    }
    assert expected.issubset(set(reader.fieldnames or []))
