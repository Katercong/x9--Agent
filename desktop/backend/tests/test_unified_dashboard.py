from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from x9_creator_desktop_system.backend.database import SessionLocal
from x9_creator_desktop_system.backend.main import app
from x9_creator_desktop_system.backend.models.creator import Creator
from x9_creator_desktop_system.backend.models.creator_source import CreatorSource
from x9_creator_desktop_system.backend.models.followup_task import FollowupTask
from x9_creator_desktop_system.backend.models.outreach_email import OutreachEmail
from x9_creator_desktop_system.backend.models.raw_observation import RawObservation
from x9_creator_desktop_system.backend.services import auth_service
from x9_creator_desktop_system.backend.services.gmail_sync_service import record_inbound_reply
from x9_creator_desktop_system.backend.services.post_processing import create_outreach_event
from x9_creator_desktop_system.backend.models.bd_monthly_stat import BdMonthlyStat


def _unified(client) -> dict:
    response = client.get("/api/local/dashboard/unified")
    assert response.status_code == 200, response.text
    return response.json()


def _summary(client) -> dict:
    return _unified(client)["summary"]


def _admin_client(username: str, *, role: str, department_code: str | None = "cross_border") -> TestClient:
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username=username,
            email=f"{username}@example.com",
            password="TempPass123!",
            role=role,
            department_code=department_code,
            approval_status=auth_service.ACTIVE_STATUS,
        )
        token, _ = auth_service.create_session_for_user(session, user, entry_scope="admin")
    c = TestClient(app)
    c.cookies.set(auth_service.SESSION_COOKIE, token)
    return c


def _creator(marker: str, suffix: str, *, recommendation_status: str | None = "recommended") -> Creator:
    return Creator(
        id=f"creator_unified_{marker}_{suffix}",
        platform="tiktok",
        handle=f"unified_{marker}_{suffix}",
        display_name=f"Unified {suffix}",
        email=f"unified_{marker}_{suffix}@example.com",
        has_email=1,
        department_code="cross_border",
        recommendation_status=recommendation_status,
        collected_at=datetime.now(),
    )


def test_unified_dashboard_kpis_and_state_projection(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stages = [
        ("pending_contact", None),
        ("contacted", "sent"),
        ("pending_followup", "pending_followup"),
        ("communicating", "communicating"),
        ("sample_shipped", "sample_shipped"),
        ("sample_delivered", "sample_delivered"),
        ("video_published", "video_published"),
        ("ad_authorized", "ad_authorized"),
        ("ad_running", "ad_running"),
    ]

    with SessionLocal() as session:
        session.add(
            RawObservation(
                id=f"obs_unified_{marker}",
                platform="tiktok",
                department_code="cross_border",
                source="test",
                raw_json=json.dumps({"marker": marker}),
                content_hash=f"hash_unified_{marker}",
                collected_at=datetime.now(),
            )
        )
        session.add(_creator(marker, "discovered", recommendation_status=None))
        for suffix, event_type in stages:
            creator = _creator(marker, suffix)
            session.add(creator)
            session.flush()
            if event_type:
                create_outreach_event(session, creator, event_type=event_type, actor_user_id="test_admin")
        session.commit()

    after = _summary(client)
    expected_discovered = len(stages) + 2
    expected_recommended = len(stages)
    expected_contacted = sum(1 for key, _ in stages if key not in {"pending_contact"})
    assert after["total_discovered"] == before["total_discovered"] + expected_discovered
    assert after["total_collected"] == before["total_collected"] + 1
    assert after["today_discovered"] == before["today_discovered"] + 1
    assert after["today_collected"] == before["today_collected"] + 1
    assert after["total_recommended"] == before["total_recommended"] + expected_recommended
    assert after["total_contacted"] == before["total_contacted"] + expected_contacted
    assert after["today_contacted"] == before["today_contacted"] + expected_contacted
    for key, _event_type in stages:
        assert after[key] == before[key] + 1
    assert after["pending_reply"] == after["pending_followup"]


def test_unified_dashboard_contacted_uses_rolling_24_hour_window(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    now = datetime.now()

    with SessionLocal() as session:
        recent_creator = _creator(marker, "recent_contacted")
        old_creator = _creator(marker, "old_contacted")
        session.add_all([recent_creator, old_creator])
        session.flush()
        session.add_all([
            OutreachEmail(
                id=f"outreach_recent_24h_{marker}",
                department_code="cross_border",
                creator_id=recent_creator.id,
                to_email=recent_creator.email,
                from_email="sender@example.com",
                subject="recent",
                body="recent",
                status="sent",
                sent_at=now - timedelta(hours=23, minutes=59),
            ),
            OutreachEmail(
                id=f"outreach_old_24h_{marker}",
                department_code="cross_border",
                creator_id=old_creator.id,
                to_email=old_creator.email,
                from_email="sender@example.com",
                subject="old",
                body="old",
                status="sent",
                sent_at=now - timedelta(hours=24, minutes=1),
            ),
        ])
        session.commit()

    after = _summary(client)

    assert after["today_contacted"] == before["today_contacted"] + 1


def test_today_duplicate_creators_counts_repeat_sources(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    old = datetime.now() - timedelta(days=2)

    with SessionLocal() as session:
        creator = _creator(marker, "duplicate_today")
        creator.collected_at = old
        creator.created_at = old
        observation = RawObservation(
            id=f"obs_duplicate_{marker}",
            platform="tiktok",
            department_code="cross_border",
            source="test",
            raw_json=json.dumps({"marker": marker, "duplicate": True}),
            content_hash=f"hash_duplicate_{marker}",
            collected_at=datetime.now(),
        )
        session.add_all([creator, observation])
        session.flush()
        session.add(
            CreatorSource(
                id=f"src_duplicate_{marker}",
                creator_id=creator.id,
                department_code="cross_border",
                source_type="tiktok_shop",
                platform="tiktok",
                handle=creator.handle,
                raw_observation_id=observation.id,
                first_seen_at=old,
                last_seen_at=datetime.now(),
            )
        )
        session.commit()

    after = _summary(client)
    assert after["today_discovered"] == before["today_discovered"] + 1
    assert after["today_duplicate_creators"] == before["today_duplicate_creators"] + 1


def test_total_contacted_includes_bd_history(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with SessionLocal() as session:
        session.add(
            BdMonthlyStat(
                id=f"bdm_unified_{marker}",
                department_code="cross_border",
                owner_name=f"BD Unified {marker}",
                month="2099-01",
                contacted=11,
                confirmed=0,
                samples=0,
                videos=0,
                source_staff_id=f"staff_unified_{marker}",
            )
        )
        session.commit()

    after = _summary(client)
    assert after["total_contacted"] == before["total_contacted"] + 11
    assert after["today_contacted"] == before["today_contacted"]


def test_sample_shipped_does_not_auto_deliver_and_creates_logistics_task(client):
    before = _summary(client)
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    old = datetime.now() - timedelta(days=15)

    with SessionLocal() as session:
        creator = _creator(marker, "old_sample")
        creator.collected_at = old
        session.add(creator)
        session.flush()
        create_outreach_event(session, creator, event_type="sample_shipped", actor_user_id="test_admin", event_at=old)
        session.commit()
        creator_id = creator.id

    after = _summary(client)
    assert after["sample_shipped"] == before["sample_shipped"] + 1
    assert after["sample_delivered"] == before["sample_delivered"]
    with SessionLocal() as session:
        task = session.query(FollowupTask).filter_by(creator_id=creator_id, task_type="fill_tracking_info").first()
        assert task is not None
        assert task.status == "open"


def test_gmail_inbound_reply_moves_contacted_to_pending_followup(client):
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")

    with SessionLocal() as session:
        creator = _creator(marker, "gmail_reply")
        session.add(creator)
        session.flush()
        email = OutreachEmail(
            id=f"email_unified_{marker}",
            department_code="cross_border",
            creator_id=creator.id,
            to_email=creator.email,
            from_email="sender@example.com",
            subject="Hello",
            body="Hello",
            status="sent",
            gmail_message_id=f"msg_{marker}",
            gmail_thread_id=f"thread_{marker}",
            sent_at=datetime.utcnow(),
        )
        session.add(email)
        create_outreach_event(
            session,
            creator,
            event_type="sent",
            actor_user_id="test_admin",
            metadata={"outreach_email_id": email.id, "gmail_thread_id": email.gmail_thread_id},
        )
        session.commit()

    before = _summary(client)
    assert before["contacted"] >= 1

    with SessionLocal() as session:
        result = record_inbound_reply(
            session,
            account_id="gmail_test_admin",
            gmail_thread_id=f"thread_{marker}",
            gmail_message_id=f"inbound_{marker}",
        )
        assert result["matched"] is True
        session.commit()
        creator_after = session.get(Creator, result["creator_id"])
        assert creator_after is not None
        assert creator_after.current_status == "待跟进"
        open_reply_tasks = (
            session.query(FollowupTask)
            .filter(FollowupTask.creator_id == result["creator_id"])
            .filter(FollowupTask.task_type == "reply_followup_1")
            .filter(FollowupTask.status.in_(("open", "pending")))
            .count()
        )
        assert open_reply_tasks == 1

    after = _summary(client)
    assert after["pending_followup"] == before["pending_followup"] + 1
    assert after["pending_reply"] == after["pending_followup"]


def test_unified_dashboard_department_scope():
    marker = datetime.now().strftime("%Y%m%d%H%M%S%f")
    dept_client = _admin_client(f"dept_unified_{marker}", role="department_admin", department_code="cross_border")
    company_client = _admin_client(f"company_unified_{marker}", role="company_admin", department_code=None)
    dept_before = _summary(dept_client)
    company_before = _summary(company_client)

    with SessionLocal() as session:
        cross = _creator(marker, "cross_scope")
        foreign = _creator(marker, "foreign_scope")
        foreign.department_code = "foreign_trade"
        session.add_all([cross, foreign])
        session.commit()

    dept_after = _summary(dept_client)
    company_after = _summary(company_client)
    assert dept_after["total_discovered"] == dept_before["total_discovered"] + 1
    assert company_after["total_discovered"] == company_before["total_discovered"] + 2
