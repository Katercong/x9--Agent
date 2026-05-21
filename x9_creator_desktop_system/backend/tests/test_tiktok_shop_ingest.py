"""TikTok Shop v2.2 ingestion + per-source attribution + feed/stats.

Covers the fixes:
* RawObservation is persisted before the contact gate (audit trail kept).
* No-contact Shop observations stay in raw audit only and do not create
  Creator rows.
* Shop list/detail fields are promoted onto Creator (source, lead_status,
  avatar_url, shop_profile_url, tiktok_shop_json) while the 1.5MB
  raw_dom_html stays only in raw_observations.
* creators.source is set per acquisition channel for the 3 dashboards.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation
from x9_creator_desktop_system.backend.routers.collector import _observation_day


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


def _add_contact(payload: dict, email: str) -> dict:
    payload["tiktok_shop"]["raw_visible_text"] = (
        str(payload["tiktok_shop"].get("raw_visible_text") or "")
        + f"\nContact {email}\n"
    )
    return payload


def test_shop_list_observation_without_contact_keeps_raw_only(client):
    payload = _shop_list_payload("shop_list_creator")
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "skipped"
    assert body["reason"] == "missing_contact"
    assert body.get("observation_id")

    db = SessionLocal()
    try:
        obs = db.get(RawObservation, body["observation_id"])
        assert obs is not None and obs.platform == "tiktok_shop"
        assert db.query(Creator).filter_by(handle="shop_list_creator").count() == 0
    finally:
        db.close()


def test_shop_existing_contact_creator_accepts_no_contact_list_metrics(client):
    detail = _add_contact(_shop_detail_payload("shop_list_creator_with_contact"), "shop.list.creator@example.com")
    client.post("/api/local/collector/observations", json=detail)
    r = client.post("/api/local/collector/observations", json=_shop_list_payload("shop_list_creator_with_contact"))
    assert r.status_code == 200
    assert r.json()["action"] == "updated"

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_list_creator_with_contact").one()
        assert c.source == "tiktok_shop"
        assert c.followers_count == 12300
        assert c.avatar_url == "https://p16.tiktokcdn.com/x.jpg"
        assert c.lead_status == "shop_profile_collected"
        metrics = json.loads(c.tiktok_shop_json)
        assert metrics["gmv_raw"] == "$1.2K"
        assert metrics["category_text"] == "Beauty"
        assert metrics["invite_status"] == "Invite"
        assert metrics["detail_captured"] is True
    finally:
        db.close()


def test_shop_detail_updates_same_creator_and_excludes_raw_dom(client):
    r2 = client.post("/api/local/collector/observations", json=_add_contact(_shop_detail_payload("shop_dual"), "shop.dual@example.com"))
    assert r2.json()["action"] == "inserted"

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_dual").one()
        assert c.lead_status == "shop_profile_collected"
        assert c.shop_profile_url.endswith("/connection/creator/detail?id=x")
        metrics = json.loads(c.tiktok_shop_json)
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


def test_shop_detail_enrichment_promotes_contact_and_snapshot(client):
    payload = _shop_detail_payload("shop_enriched_contact")
    payload["creator"]["followers_raw"] = None
    payload["tiktok_shop"]["raw_visible_text"] = (
        "Shop creator profile\n"
        "33.4K followers\n"
        "Contact shop.enriched@example.com\n"
        "More links https://linktr.ee/shop_enriched_contact"
    )
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_enriched_contact").one()
        assert c.email == "shop.enriched@example.com"
        assert c.followers_count == 33400
        assert "linktr.ee/shop_enriched_contact" in (c.external_links_json or "")
        snapshot = json.loads(c.profile_snapshot_json or "{}")
        assert "tiktok_shop.raw_visible_text" in snapshot["source_text_fields"]
        assert "shop.enriched@example.com" in snapshot["emails"]
    finally:
        db.close()


def test_shop_detail_text_metrics_are_structured_server_side(client):
    payload = _add_contact(_shop_detail_payload("shop_detail_structured"), "shop.detail.structured@example.com")
    payload["creator"]["followers_raw"] = "2"
    payload["creator"]["followers_count"] = 2
    payload["tiktok_shop"]["raw_visible_text"] = (
        "Creator details\n"
        "shop_detail_structured\n"
        "Rating\n"
        "Not yet rated\n"
        "Categories\n"
        "Beauty & Personal Care\n"
        "Followers\n"
        "114.2K\n"
        "Flat fee\n"
        "Eligible for flat fee\n"
        "Contact shop.detail.structured@example.com\n"
        "PPS\n"
        "Sample score\n"
        "93/ 100Excellent\n"
        "Sales\n"
        "GMV\n"
        "$174.9K\n"
        "Items sold\n"
        "7.83K\n"
        "GPM\n"
        "$27.1\n"
        "GMV per customer\n"
        "$27.8\n"
        "Collaboration metrics\n"
        "Est. post rate\n"
        "87.4%\n"
        "Avg. commission rate\n"
        "15%\n"
        "Products\n"
        "634\n"
        "Brand collaborations\n"
        "22\n"
        "Video\n"
        "Video GPM\n"
        "$27.1\n"
        "Videos\n"
        "112\n"
        "Avg. video views\n"
        "2.69K\n"
        "Avg. video engagement rate\n"
        "1.58%\n"
        "LIVE\n"
        "LIVE GPM\n"
        "$0.00\n"
        "LIVE streams\n"
        "0\n"
        "Avg. LIVE views\n"
        "0\n"
        "Avg. LIVE engagement rate\n"
        "0%\n"
        "Followers\n"
        "Gender\n"
        "Male\n"
        "38.48%\n"
        "Female\n"
        "61.52%\n"
    )
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_detail_structured").one()
        assert c.email == "shop.detail.structured@example.com"
        assert c.followers_raw == "114.2K"
        assert c.followers_count == 114200
        metrics = json.loads(c.tiktok_shop_json or "{}")
        assert metrics["gmv_raw"] == "$174.9K"
        assert metrics["gpm_raw"] == "$27.1"
        assert metrics["avg_commission_rate_raw"] == "15%"
        assert metrics["category_text"] == "Beauty & Personal Care"
        assert metrics["female_pct_raw"] == "61.52%"
    finally:
        db.close()

    feed = client.get("/api/local/collector/observations-feed?source=tiktok_shop&limit=100").json()
    row = next(it for it in feed["items"] if it["handle"] == "shop_detail_structured")
    assert row["followers_raw"] == "114.2K"
    assert row["shop"]["gmv_raw"] == "$174.9K"
    assert row["shop"]["category_text"] == "Beauty & Personal Care"
    assert row["lead"]["email"] == "shop.detail.structured@example.com"


def test_shop_detail_invalid_heading_uses_valid_display_name_handle(client):
    payload = _shop_detail_payload("placeholder_handle")
    payload["creator"]["handle"] = "j nyc"
    payload["creator"]["display_name"] = "dainty.nugs"
    payload["creator"]["profile_url"] = None
    payload["tiktok_shop"]["raw_capture"]["page_title"] = "TikTok Shop"
    payload["tiktok_shop"]["raw_capture"]["links"] = []
    payload["tiktok_shop"]["raw_visible_text"] = (
        "Creator detail\n"
        "j nyc\n"
        "dainty.nugs\n"
        "Contact dainty.nugs@example.com\n"
    )
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200
    assert r.json()["handle"] == "dainty.nugs"

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="dainty.nugs").one()
        assert c.display_name == "j nyc"
        assert db.query(Creator).filter_by(handle="j nyc").count() == 0
    finally:
        db.close()


def test_shop_raw_detail_text_becomes_server_side_scoring_signal(client):
    payload = _shop_detail_payload("shop_scoring_signal")
    payload["tiktok_shop"]["raw_visible_text"] = (
        "TikTok Shop creator profile\n"
        "Beauty skincare haul review creator\n"
        "Affiliate commission available\n"
        "GMV $8.2K\n"
        "GPM 18%\n"
        "Audience Female 79%\n"
        "Contact shop.scoring@example.com\n"
    )
    r = client.post("/api/local/collector/observations", json=payload)
    assert r.status_code == 200

    db = SessionLocal()
    try:
        c = db.query(Creator).filter_by(handle="shop_scoring_signal").one()
        metrics = json.loads(c.tiktok_shop_json or "{}")
        assert metrics["has_detail_text"] is True
        assert "detail_text_excerpt" in metrics
        assert "detail_signal_lines" in metrics
        assert c.content_format_score > 0
        assert c.commercial_value_score > 0
        assert c.data_quality_score >= 60
    finally:
        db.close()


def test_shop_feed_and_source_stats(client):
    client.post("/api/local/collector/observations", json=_shop_list_payload("shop_feed_a"))
    client.post("/api/local/collector/observations", json=_add_contact(_shop_detail_payload("shop_feed_a"), "shop.feed@example.com"))

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


def test_source_stats_today_uses_collected_at(client):
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    handle = f"shop_collected_today_{now:%Y%m%d%H%M%S%f}"
    payload = {
        "creator": {"handle": handle, "display_name": "Collected Today"},
        "lead_status": "shop_list_seen",
    }

    db = SessionLocal()
    try:
        db.add(
            RawObservation(
                id=f"obs_{handle}",
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop_creator_lead_browser_extension_2_2",
                worker_id="shop_worker",
                raw_json=json.dumps(payload),
                content_hash=f"hash_{handle}",
                created_at=yesterday,
                collected_at=now,
            )
        )
        db.commit()
    finally:
        db.close()

    stats = client.get("/api/local/collector/source-stats").json()["sources"]["tiktok_shop"]
    assert stats["today"] >= 1


def test_source_stats_day_parses_sqlite_text_timestamp():
    assert _observation_day(None, "2026-05-19 12:47:22.395").isoformat() == "2026-05-19"
    assert _observation_day(None, "2026-05-19T12:47:22.395Z").isoformat() == "2026-05-19"


def test_source_stats_funnel_counts_late_lead_status(client):
    before = client.get("/api/local/collector/source-stats").json()["sources"]["tiktok_shop"]["funnel"]["shop_profile_collected"]
    handle = f"shop_late_status_{datetime.now():%Y%m%d%H%M%S%f}"
    payload = {
        "event_type": "creator_observation",
        "platform": "tiktok_shop",
        "creator": {"handle": handle, "display_name": "Late Status"},
        "tiktok_shop": {"raw_dom_html": "x" * 5000},
        "lead_status": "shop_profile_collected",
    }
    db = SessionLocal()
    try:
        db.add(
            RawObservation(
                id=f"obs_{handle}",
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop_creator_lead_browser_extension_2_2",
                raw_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                content_hash=f"hash_{handle}",
                collected_at=datetime.now(),
            )
        )
        db.commit()
    finally:
        db.close()

    after = client.get("/api/local/collector/source-stats").json()["sources"]["tiktok_shop"]["funnel"]["shop_profile_collected"]
    assert after == before + 1


def test_reprocess_raw_two_pass_merges_skipped_list_metrics(client):
    handle = "shop_reprocess_merge"
    client.post("/api/local/collector/observations", json=_shop_list_payload(handle))
    client.post("/api/local/collector/observations", json=_add_contact(_shop_detail_payload(handle), "shop.reprocess@example.com"))

    db = SessionLocal()
    try:
        before_count = db.query(RawObservation).filter_by(platform="tiktok_shop").count()
        c = db.query(Creator).filter_by(handle=handle).one()
        assert "gmv_raw" not in json.loads(c.tiktok_shop_json or "{}")
    finally:
        db.close()

    r = client.post("/api/local/collector/reprocess-raw", json={"platform": "tiktok_shop", "limit": 1000})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    db = SessionLocal()
    try:
        assert db.query(RawObservation).filter_by(platform="tiktok_shop").count() == before_count
        c = db.query(Creator).filter_by(handle=handle).one()
        metrics = json.loads(c.tiktok_shop_json or "{}")
        assert metrics["gmv_raw"] == "$1.2K"
        assert c.email == "shop.reprocess@example.com"
    finally:
        db.close()


def test_source_attribution_three_buckets(client):
    client.post("/api/local/collector/observations", json=_add_contact(_shop_detail_payload("attr_shop"), "attr.shop@example.com"))
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
