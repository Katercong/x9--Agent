from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.creator_source import CreatorSource
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation


def _summary(client) -> dict:
    response = client.get("/api/local/dashboard/department-summary")
    assert response.status_code == 200
    return response.json()["summary"]


def _dashboard(client) -> dict:
    response = client.get("/api/local/dashboard/department-summary")
    assert response.status_code == 200
    return response.json()


def _today_trend(payload: dict) -> dict:
    today = datetime.now().date().isoformat()
    return next(row for row in payload["analytics"]["trend"] if row["date"] == today)


def test_business_summary_counts_cumulative_creator_rows(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with SessionLocal() as session:
        session.add(
            RawObservation(
                id=f"obs_dashboard_raw_{marker}",
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop_creator_lead_browser_extension_2_2",
                raw_json=json.dumps({
                    "event_type": "creator_observation",
                    "platform": "tiktok_shop",
                    "creator": {"handle": f"dashboard_raw_only_{marker}"},
                    "lead_status": "shop_list_seen",
                }, ensure_ascii=False, separators=(",", ":")),
                content_hash=f"hash_dashboard_raw_{marker}",
                collected_at=datetime.now(),
            )
        )
        session.commit()

    after_raw = _summary(client)
    assert after_raw["total_creators"] == before["total_creators"] + 1
    assert after_raw["today_new_creators"] == before["today_new_creators"] + 1
    assert after_raw["raw_observations_total"] == before.get("raw_observations_total", 0) + 1

    with SessionLocal() as session:
        creator = Creator(
            id=f"creator_dashboard_{marker}",
            platform="tiktok",
            handle=f"dashboard_creator_{marker}",
            display_name="Dashboard Creator",
            department_code="cross_border",
            source="x9_leads",
            current_status="prospect",
            collected_at=datetime.now(),
        )
        session.add(creator)
        session.add(CreatorSource(
            id=f"src_dashboard_{marker}",
            creator_id=creator.id,
            platform=creator.platform,
            handle=creator.handle,
            department_code="cross_border",
            source_type="tiktok_video",
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        ))
        session.commit()

    after_creator = _summary(client)
    assert after_creator["total_creators"] == after_raw["total_creators"] + 1
    assert after_creator["today_new_creators"] == after_raw["today_new_creators"] + 1
    assert after_creator["processed_creators"] == after_raw.get("processed_creators", 0) + 1


def test_business_summary_migrates_bd_history_without_faking_creators(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with SessionLocal() as session:
        session.execute(text(
            """
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                role TEXT,
                note TEXT,
                department_code TEXT
            )
            """
        ))
        session.execute(
            text("INSERT INTO staff (name, role, note, department_code) VALUES (:name, :role, :note, :department_code)"),
            {
                "name": f"BD Dashboard {marker}",
                "role": "bd",
                "department_code": "cross_border",
                "note": json.dumps({"contacted": 7, "confirmed": 3, "samples": 2, "videos": 1}, ensure_ascii=False),
            },
        )
        session.commit()

    after = _summary(client)
    assert after["total_creators"] == before["total_creators"]
    assert after["business_with_bd_history_total"] == before.get("business_with_bd_history_total", before["total_creators"]) + 7
    assert after["bd_history_contacted"] == before.get("bd_history_contacted", 0) + 7
    assert after["bd_history_confirmed"] == before.get("bd_history_confirmed", 0) + 3

    payload = _dashboard(client)
    member = next(row for row in payload["analytics"]["members"] if row["member"] == f"BD Dashboard {marker}")
    assert member["total_contacted"] == 7
    assert member["bd_history_contacted"] == 7
    assert member["bd_history_confirmed"] == 3


def test_company_analytics_trend_includes_total_collected_excluding_queue(client):
    before = _dashboard(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with SessionLocal() as session:
        session.add_all([
            RawObservation(
                id=f"obs_dashboard_collected_{marker}",
                platform="tiktok_shop",
                department_code="cross_border",
                source="test",
                raw_json=json.dumps({"marker": marker, "kind": "collected"}),
                content_hash=f"hash_dashboard_collected_{marker}",
                lead_status="processed",
                collected_at=datetime.now(),
            ),
            RawObservation(
                id=f"obs_dashboard_queue_{marker}",
                platform="tiktok_shop",
                department_code="cross_border",
                source="test",
                raw_json=json.dumps({"marker": marker, "kind": "queue"}),
                content_hash=f"hash_dashboard_queue_{marker}",
                lead_status="shop_list_seen",
                collected_at=datetime.now(),
            ),
        ])
        session.commit()

    after = _dashboard(client)
    assert _today_trend(after)["collected"] == _today_trend(before).get("collected", 0) + 1
