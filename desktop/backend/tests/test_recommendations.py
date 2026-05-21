from __future__ import annotations

from datetime import datetime

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.creator_source import CreatorSource


def test_recommendations_return_one_row_per_creator(client):
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    creator_id = f"rec_dedup_{marker}"
    with SessionLocal() as session:
        session.add(
            Creator(
                id=creator_id,
                platform="tiktok",
                handle=f"rec_dedup_{marker}",
                display_name="Recommendation Dedup",
                department_code="cross_border",
                recommendation_status="recommended",
                recommendation_score=90,
                collected_at=datetime.now(),
            )
        )
        session.add_all(
            [
                CreatorSource(
                    id=f"rec_dedup_src_a_{marker}",
                    creator_id=creator_id,
                    department_code="cross_border",
                    source_type="tiktok_shop",
                    platform="tiktok",
                    handle=f"rec_dedup_{marker}",
                    first_seen_at=datetime.now(),
                    last_seen_at=datetime.now(),
                ),
                CreatorSource(
                    id=f"rec_dedup_src_b_{marker}",
                    creator_id=creator_id,
                    department_code="cross_border",
                    source_type="tiktok_shop",
                    platform="tiktok",
                    handle=f"rec_dedup_{marker}",
                    first_seen_at=datetime.now(),
                    last_seen_at=datetime.now(),
                ),
            ]
        )
        session.commit()

    response = client.get("/api/local/recommendations?source_type=tiktok_shop&limit=100")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids.count(creator_id) == 1
