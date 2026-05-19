from __future__ import annotations

import json
from datetime import datetime

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.outreach_email import OutreachEmail
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation
from x9_creator_desktop_system.backend.services import auth_service


def test_auth_users_include_collection_creator_and_outreach_stats(client):
    marker = "stats_user"
    username = f"{marker}_bd"
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username=username,
            password="X9@Test123",
            role="department_user",
            department_code="cross_border",
            display_name="Stats BD",
            is_active=True,
            approval_status="active",
        )
        creator = Creator(
            id=f"creator_{marker}",
            platform="tiktok",
            department_code="cross_border",
            handle=f"{marker}_creator",
            email="creator@example.com",
            owner_bd=username,
            current_status="contacted",
        )
        db.add(creator)
        db.add(RawObservation(
            id=f"obs_{marker}",
            platform="tiktok",
            department_code="cross_border",
            source="test",
            raw_json=json.dumps({"event_type": "creator_observation", "creator": {"handle": f"{marker}_creator"}}),
            content_hash=f"hash_{marker}",
            collected_at=datetime.utcnow(),
        ))
        db.add(OutreachEmail(
            id=f"oem_{marker}",
            department_code="cross_border",
            creator_id=creator.id,
            to_email="creator@example.com",
            subject="hello",
            body="body",
            status="sent",
            created_by=user.id,
            sent_at=datetime.utcnow(),
        ))
        db.commit()

    response = client.get("/api/local/auth/users")
    assert response.status_code == 200
    row = next(item for item in response.json()["items"] if item["username"] == username)
    stats = row["stats"]
    assert stats["collection"]["scope"] == "department"
    assert stats["collection"]["total"] >= 1
    assert stats["collection"]["today"] >= 1
    assert stats["creators"]["owned"] >= 1
    assert stats["creators"]["contacted"] >= 1
    assert stats["outreach"]["total"] >= 1
    assert stats["outreach"]["sent"] >= 1
    assert stats["outreach"]["last_at"]
