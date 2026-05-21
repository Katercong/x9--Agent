from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation


def _summary(client) -> dict:
    response = client.get("/api/local/dashboard/department-summary")
    assert response.status_code == 200
    return response.json()["summary"]


def test_business_summary_counts_all_channel_rows_without_dedup(client):
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
    assert after_raw["progressed"] == before["progressed"]
    assert after_raw["today_collected"] == after_raw["today_new_creators"]
    assert after_raw["raw_observations_today"] == before["raw_observations_today"] + 1

    with SessionLocal() as session:
        session.add(
            Creator(
                id=f"creator_dashboard_{marker}",
                platform="tiktok",
                handle=f"dashboard_creator_{marker}",
                display_name="Dashboard Creator",
                department_code="cross_border",
                source="x9_leads",
                current_status="video_published",
                collected_at=datetime.now(),
            )
        )
        session.commit()

    after_creator = _summary(client)
    assert after_creator["total_creators"] == before["total_creators"] + 2
    assert after_creator["today_new_creators"] == before["today_new_creators"] + 2
    assert after_creator["progressed"] == before["progressed"] + 1
    assert after_creator["today_collected"] == after_creator["today_new_creators"]


def test_business_summary_includes_bd_history_as_creator_data(client):
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
    assert after["total_creators"] == before["total_creators"] + 7
    assert after["contacted"] == before["contacted"] + 7
    assert after["progressed"] == before["progressed"] + 3
    assert after["bd_history_creators"] == before.get("bd_history_creators", 0) + 7
