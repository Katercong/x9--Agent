"""TikTok Shop v2.2 ingestion + per-source attribution + feed/stats.

Covers the fixes:
* RawObservation is persisted before the contact gate (audit trail kept).
* The contact gate is bypassed for tiktok_shop, so Shop creators (no email
  at collection time) DO get a Creator row.
* Shop list/detail fields are promoted onto Creator (source, lead_status,
  avatar_url, shop_profile_url, tiktok_shop_json) while the 1.5MB
  raw_dom_html stays only in raw_observations.
* creators.source is set per acquisition channel for the 3 dashboards.
"""
from __future__ import annotations

import json

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation


def _shop_list_payload(handle: str) -> dict:
    return {
        "event_type": "creator_observation",
        "platform": "tiktok_shop",
        "source": "tiktok_shop_creator_lead_browser_extension_2_2",
        "worker_id": "shop_worker",
        "run_id": "run-20260518000000",
        "lead_status": "shop_list_seen",
        "collected_at": "2026-05-18T00:00:01.000Z",
        "creator": {
            "handle": handle,
            "display_name": "Shop Creator",
            "profile_url": f"https://www.tiktok.com/@{handle}",
            "shop_profile_url": None,
            "avatar_url": "https://p16.tiktokcdn.com/x.jpg",
            "followers_raw": "12.3K",
            "followers_count": None,
        },
        "tiktok_shop": {
            "list_item": {
                "handle": handle,
                "gmv_raw": "$1.2K",
                "gpm_raw": "32%",
                "avg_commission_rate_raw": "15%",
                "category_text": "Beauty",
                "invite_status": "Invite",
                "save_status": "Save",
                "row_index": 7,
                "source_page_url": "https://affiliate-us.tiktok.com/connection/creator",
                "collected_at": "2026-05-18T00:00:01.000Z",
            }
        },
    }


def _shop_detail_payload(handle: str) -> dict:
    return {
        "event_type": "creator_observation",
        "platform": "tiktok_shop",
        "source": "tiktok_shop_creator_lead_browser_extension_2_2",
        "worker_id": "shop_worker",
        "lead_status": "shop_profile_collected",
        "collected_at": "2026-05-18T00:05:00.000Z",
        "creator": {
            "handle": handle,
            "display_name": "Shop Creator",
            "profile_url": f"https://www.tiktok.com/@{handle}",
            "shop_profile_url": "https://affiliate-us.tiktok.com/connection/creator/detail?id=x",
            "followers_raw": "12.3K",
        },
        "tiktok_shop": {
            "source_page_url": "https://affiliate-us.tiktok.com/connection/creator/detail?id=x",
            "raw_capture": {
                "page_title": f"{handle} | TikTok Shop",
                "captured_at": "2026-05-18T00:05:00.000Z",
                "links": ["https://www.tiktok.com/@" + handle, "https://linktr.ee/" + handle],
            },
            "raw_visible_text": "visible " * 500,
            "raw_dom_html": "<html><body>" + ("x" * 8000) + "</body></html>",
        },
    }


def test_shop_list_observation_creates_creator_without_contact(client):
    payload = _shop_list_payload("shop_list_creator")
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    body = r.json()
    # Gate is bypassed for tiktok_shop -> Creator IS created (no email needed).
    assert body["action"] == "inserted"
    assert body.get("observation_id")

    db = SessionLocal()
    try:
        obs = db.get(RawObservation, body["observation_id"])
        assert obs is not None and obs.platform == "tiktok_shop"
        c = db.query(Creator).filter_by(handle="shop_list_creator").one()
        assert c.source == "tiktok_shop"
        assert c.followers_count == 12300
        assert c.avatar_url == "https://p16.tiktokcdn.com/x.jpg"
        assert c.lead_status == "shop_list_seen"
        metrics = json.loads(c.tiktok_shop_json)
        assert metrics["gmv_raw"] == "$1.2K"
        assert metrics["category_text"] == "Beauty"
        assert metrics["invite_status"] == "Invite"
        assert metrics["detail_captured"] is False
    finally:
        db.close()


def test_shop_detail_updates_same_creator_and_excludes_raw_dom(client):
    client.post("/api/local/collector/observations", json=_shop_list_payload("shop_dual"))
    r2 = client.post("/api/local/collector/observations", json=_shop_detail_payload("shop_dual"))
    assert r2.json()["action"] == "updated"

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_dual").one()
        assert c.lead_status == "shop_profile_collected"
        assert c.shop_profile_url.endswith("/connection/creator/detail?id=x")
        metrics = json.loads(c.tiktok_shop_json)
        # list-phase fields survive the detail merge
        assert metrics["gmv_raw"] == "$1.2K"
        assert metrics["detail_captured"] is True
        assert metrics["detail_links_count"] == 2
        # the 1.5MB-class blob must never be promoted onto the Creator
        assert "<html>" not in (c.tiktok_shop_json or "")
        assert not hasattr(c, "raw_dom_html")
        # ...but the detail audit row keeps the full payload (incl. raw_dom_html)
        detail_obs = (
            db.query(RawObservation)
            .filter(
                RawObservation.platform == "tiktok_shop",
                RawObservation.raw_json.like("%raw_dom_html%"),
            )
            .first()
        )
        assert detail_obs is not None
    finally:
        db.close()


def test_shop_feed_and_source_stats(client):
    client.post("/api/local/collector/observations", json=_shop_list_payload("shop_feed_a"))
    client.post("/api/local/collector/observations", json=_shop_detail_payload("shop_feed_a"))

    feed = client.get("/api/local/collector/observations-feed?source=tiktok_shop&limit=100").json()
    assert feed["ok"] is True
    rows = [it for it in feed["items"] if it["handle"] == "shop_feed_a"]
    assert rows
    list_row = next(it for it in rows if it["shop"]["lead_status"] == "shop_list_seen")
    assert list_row["shop"]["gmv_raw"] == "$1.2K"
    detail_row = next(it for it in rows if it["shop"]["lead_status"] == "shop_profile_collected")
    assert detail_row["shop"]["detail_captured"] is True
    assert "raw_dom_html" not in detail_row.get("shop", {})

    stats = client.get("/api/local/collector/source-stats").json()
    shop = stats["sources"]["tiktok_shop"]
    assert shop["total"] >= 2
    assert shop["funnel"]["shop_list_seen"] >= 1
    assert shop["funnel"]["shop_profile_collected"] >= 1
    assert len(shop["daily"]) == 7


def test_source_attribution_three_buckets(client):
    client.post("/api/local/collector/observations", json=_shop_list_payload("attr_shop"))
    client.post("/api/local/extension/x9-compat/ingest-creators", json={
        "items": [{
            "handle": "attr_x9_lead",
            "platform": "tiktok",
            "profile_url": "https://www.tiktok.com/@attr_x9_lead",
            "display_name": "X9 Lead",
            "bio": "collab dm",
            "followers": 12300,
            "email": "attr_x9_lead@gmail.com",
            "external_links": ["https://linktr.ee/attr_x9_lead"],
            "source_video_url": "https://www.tiktok.com/@attr_x9_lead/video/1",
            "notes": "keyword=beauty filter=qualified",
        }]
    })
    csv_body = (
        "handle,platform,display_name,bio,followers,email,whatsapp,instagram_handle,source\n"
        "attr_import_creator,tiktok,Import Creator,UGC creator,25000,,15551234567,@attr_ig,table_test\n"
    ).encode("utf-8")
    client.post(
        "/api/local/import/creators/table?filename=creators.csv",
        content=csv_body,
        headers={"Content-Type": "text/csv"},
    )

    db = SessionLocal()
    try:
        assert db.query(Creator).filter_by(handle="attr_shop").one().source == "tiktok_shop"
        assert db.query(Creator).filter_by(handle="attr_x9_lead").one().source == "x9_leads"
        assert db.query(Creator).filter_by(handle="attr_import_creator").one().source == "table_import"
    finally:
        db.close()

    stats = client.get("/api/local/collector/source-stats").json()["sources"]
    assert stats["tiktok_shop"]["total"] >= 1
    assert stats["x9_leads"]["total"] >= 1
    assert stats["table_import"]["total"] >= 1

    x9 = client.get("/api/local/collector/observations-feed?source=x9_leads&limit=100").json()
    assert any(it["handle"] == "attr_x9_lead" and it["lead"]["email"] for it in x9["items"])
    imp = client.get("/api/local/collector/observations-feed?source=table_import&limit=100").json()
    assert any(it["handle"] == "attr_import_creator" for it in imp["items"])
