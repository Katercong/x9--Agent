from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from desktop.backend.database import SessionLocal, init_db
from desktop.backend.main import app
from desktop.backend.models.creator import Creator
from desktop.backend.models.creator_source import CreatorSource
from desktop.backend.models.extension_session import ExtensionSession
from desktop.backend.models.raw_observation import RawObservation
from desktop.backend.services.collection_stats_service import get_actor_collection_stats_map, get_source_stats
from desktop.backend.services import auth_service


def _make_user_client(username: str) -> tuple[TestClient, str]:
    init_db()
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username=username,
            password="X9@Test123",
            role="department_user",
            department_code="cross_border",
            display_name=username,
            is_active=True,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        user_id = user.id
        token, _ = auth_service.create_session_for_user(db, user)
    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    return client, user_id


def _make_admin_client(username: str) -> tuple[TestClient, str]:
    init_db()
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username=username,
            password="X9@Test123",
            role="department_admin",
            department_code="cross_border",
            display_name=username,
            is_active=True,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        user_id = user.id
        token, _ = auth_service.create_session_for_user(db, user, entry_scope="admin")
    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    return client, user_id


def _shop_payload(handle: str, worker_id: str) -> dict:
    return {
        "event_type": "creator_observation",
        "platform": "tiktok_shop",
        "source": "tiktok_shop",
        "worker_id": worker_id,
        "account_id": worker_id,
        "extension_id": "test_extension",
        "creator": {
            "handle": handle,
            "display_name": handle,
            "profile_url": f"https://www.tiktok.com/@{handle}",
            "shop_profile_url": f"https://affiliate-us.tiktok.com/connection/creator/detail?handle={handle}",
            "email": f"{handle}@example.com",
        },
        "tiktok_shop": {
            "list_item": {
                "category_text": "Beauty",
                "gmv_raw": "$1K",
            },
        },
        "lead_status": "shop_profile_collected",
        "collected_at": datetime.utcnow().isoformat(),
    }


def test_worker_self_bind_backfills_unassigned_shop_rows():
    client, actor_id = _make_user_client("bind_backfill_user")
    worker_id = "test_worker_bind_backfill"
    handle = "bind_backfill_creator"
    raw_id = "raw_bind_backfill"
    creator_id = "creator_bind_backfill"

    with SessionLocal() as db:
        db.add(
            RawObservation(
                id=raw_id,
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop",
                actor_user_id=None,
                worker_id=worker_id,
                account_id=worker_id,
                raw_json=json.dumps(_shop_payload(handle, worker_id)),
                content_hash="hash_bind_backfill",
                collected_at=datetime.utcnow(),
            )
        )
        db.add(
            Creator(
                id=creator_id,
                platform="tiktok_shop",
                department_code="cross_border",
                handle=handle,
                display_name=handle,
            )
        )
        db.add(
            CreatorSource(
                id="source_bind_backfill",
                creator_id=creator_id,
                department_code="cross_border",
                source_type="tiktok_shop",
                platform="tiktok_shop",
                handle=handle,
                actor_user_id=None,
                raw_observation_id=raw_id,
                worker_id=worker_id,
                account_id=worker_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
        )
        db.commit()

    response = client.get(f"/api/local/extension/worker-self-bind?worker_id={worker_id}&backfill=true")
    assert response.status_code == 200
    body = response.json()
    assert body["actor_user_id"] == actor_id
    assert body["backfill"]["raw_observations"] == 1
    assert body["backfill"]["creator_sources"] == 1

    with SessionLocal() as db:
        raw = db.get(RawObservation, raw_id)
        source = db.get(CreatorSource, "source_bind_backfill")
        session = db.query(ExtensionSession).filter(ExtensionSession.worker_id == worker_id).one()
    assert raw.actor_user_id == actor_id
    assert source.actor_user_id == actor_id
    assert session.actor_user_id == actor_id


def test_unbound_tiktok_shop_upload_is_rejected():
    init_db()
    worker_id = "test_worker_unbound_reject"
    payload = _shop_payload("unbound_reject_creator", worker_id)
    client = TestClient(app)

    response = client.post("/api/local/collector/observations", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "actor_binding_required"
    with SessionLocal() as db:
        count = db.query(RawObservation).filter(RawObservation.worker_id == worker_id).count()
    assert count == 0


def test_bound_worker_upload_without_cookie_is_attributed():
    bound_client, actor_id = _make_user_client("bound_worker_user")
    worker_id = "test_worker_bound_upload"
    handle = "bound_upload_creator"

    bind_response = bound_client.get(f"/api/local/extension/worker-self-bind?worker_id={worker_id}")
    assert bind_response.status_code == 200

    upload_client = TestClient(app)
    response = upload_client.post("/api/local/collector/observations", json=_shop_payload(handle, worker_id))
    assert response.status_code == 200

    with SessionLocal() as db:
        raw = (
            db.query(RawObservation)
            .filter(RawObservation.worker_id == worker_id)
            .order_by(RawObservation.created_at.desc())
            .first()
        )
        source = (
            db.query(CreatorSource)
            .filter(CreatorSource.worker_id == worker_id, CreatorSource.handle == handle)
            .order_by(CreatorSource.created_at.desc())
            .first()
        )
    assert raw is not None
    assert raw.actor_user_id == actor_id
    assert source is not None
    assert source.actor_user_id == actor_id


def test_admin_user_cannot_self_bind_as_collector():
    admin_client, _ = _make_admin_client("admin_cannot_collect")

    response = admin_client.get("/api/local/extension/worker-self-bind?worker_id=test_worker_admin_blocked")

    assert response.status_code == 409
    assert response.json()["detail"] == "actor_binding_required"


def test_collection_actors_lists_collection_users_only():
    admin_client, admin_id = _make_admin_client("admin_hidden_from_collection_cards")
    _, user_id = _make_user_client("collector_card_user")

    response = admin_client.get("/api/local/collector/actors")

    assert response.status_code == 200
    items = response.json()["items"]
    assert user_id in {item["id"] for item in items}
    assert admin_id not in {item["id"] for item in items}
    assert {item["role"] for item in items} <= {"department_user"}


def test_queued_total_is_today_only_and_clears_historical_backlog():
    _, actor_id = _make_user_client("queue_today_user")
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    with SessionLocal() as db:
        db.add(
            RawObservation(
                id="raw_queue_yesterday",
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop",
                actor_user_id=actor_id,
                worker_id="worker_queue_today",
                account_id="worker_queue_today",
                lead_status="shop_list_seen",
                raw_json=json.dumps(_shop_payload("queue_yesterday", "worker_queue_today")),
                content_hash="hash_queue_yesterday",
                collected_at=yesterday,
            )
        )
        db.add(
            RawObservation(
                id="raw_queue_today",
                platform="tiktok_shop",
                department_code="cross_border",
                source="tiktok_shop",
                actor_user_id=actor_id,
                worker_id="worker_queue_today",
                account_id="worker_queue_today",
                lead_status="shop_list_seen",
                raw_json=json.dumps(_shop_payload("queue_today", "worker_queue_today")),
                content_hash="hash_queue_today",
                collected_at=now,
            )
        )
        db.commit()

        actor_stats = get_actor_collection_stats_map(db, [actor_id], department_code="cross_border")[actor_id]
        source_stats = get_source_stats(db, department_code="cross_border", actor_filter=actor_id)["sources"]["tiktok_shop"]
        assert actor_stats["sources"]["tiktok_shop"]["queued_total"] == 1
        assert source_stats["queued_total"] == 1

        creator = Creator(
            id="creator_queue_today",
            platform="tiktok_shop",
            department_code="cross_border",
            handle="queue_today",
            display_name="queue_today",
        )
        db.add(creator)
        db.add(
            CreatorSource(
                id="source_queue_today",
                creator_id=creator.id,
                department_code="cross_border",
                source_type="tiktok_shop",
                platform="tiktok_shop",
                handle="queue_today",
                actor_user_id=actor_id,
                raw_observation_id="raw_queue_today",
                worker_id="worker_queue_today",
                account_id="worker_queue_today",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        db.commit()

        actor_stats = get_actor_collection_stats_map(db, [actor_id], department_code="cross_border")[actor_id]
        source_stats = get_source_stats(db, department_code="cross_border", actor_filter=actor_id)["sources"]["tiktok_shop"]
        assert actor_stats["sources"]["tiktok_shop"]["queued_total"] == 0
        assert source_stats["queued_total"] == 0
