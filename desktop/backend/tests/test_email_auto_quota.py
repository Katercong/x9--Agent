from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from desktop.backend.database import SessionLocal
from desktop.backend.main import app
from desktop.backend.models.creator import Creator
from desktop.backend.models.email_auto import EmailAutoCampaign, EmailAutoJob, GmailAccountQuota
from desktop.backend.models.gmail_account import GmailAccount
from desktop.backend.models.outreach_email import OutreachEmail
from desktop.backend.routers import email_auto
from desktop.backend.services import auth_service


@pytest.fixture()
def client():
    with SessionLocal() as db:
        user = auth_service.upsert_user(
            db,
            username="email_auto_super",
            password="Preview@2026",
            role="super_admin",
            department_code=None,
            approval_status=auth_service.ACTIVE_STATUS,
            is_active=True,
        )
        token, _ = auth_service.create_session_for_user(db, user, entry_scope="admin")
    test_client = TestClient(app)
    test_client.cookies.set(auth_service.SESSION_COOKIE, token)
    return test_client


def test_mailbox_quota_usage_uses_rolling_24_hour_window(monkeypatch):
    now = datetime(2026, 6, 4, 12, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)
    marker = uuid.uuid4().hex
    email = f"quota-{marker}@example.com"

    with SessionLocal() as db:
        account = GmailAccount(
            id=f"gmail_{marker}",
            email=email,
            display_name="Quota Test",
            token_json="{}",
            is_active=1,
        )
        creator = Creator(
            id=f"creator_{marker}",
            platform="quota_test",
            handle=f"quota_{marker}",
            department_code="cross_border",
        )
        db.add_all([account, creator])
        db.flush()

        db.add_all([
            OutreachEmail(
                id=f"recent_{marker}",
                creator_id=creator.id,
                to_email="recent@example.com",
                from_email=email,
                subject="recent",
                body="recent",
                status="sent",
                auto_send=1,
                sent_at=now - timedelta(hours=23, minutes=59),
            ),
            OutreachEmail(
                id=f"old_{marker}",
                creator_id=creator.id,
                to_email="old@example.com",
                from_email=email,
                subject="old",
                body="old",
                status="sent",
                auto_send=1,
                sent_at=now - timedelta(hours=24, minutes=1),
            ),
        ])
        db.commit()

        assert email_auto._daily_auto_sent(db, email) == 1

        quota = GmailAccountQuota(
            id=f"gmq_{marker}",
            account_id=account.id,
            email=email,
            department_code="cross_border",
            daily_quota=150,
            synced_sent_today=7,
            synced_sent_date="rolling_24h",
        )
        db.add(quota)
        db.commit()

        assert email_auto._daily_auto_sent(db, email, quota) == 1


def test_generate_jobs_fills_to_campaign_daily_limit_even_when_limit_is_smaller(client, monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Queue Limit {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=3,
            hourly_limit=3,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index in range(4):
            db.add(Creator(
                id=f"creator_queue_{marker}_{index}",
                platform="queue_test",
                department_code="cross_border",
                handle=f"queue_{marker}_{index}",
                email=f"queue-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.add(EmailAutoJob(
            id=f"existing_job_{marker}",
            department_code="cross_border",
            campaign_id=campaign_id,
            creator_id=f"creator_queue_{marker}_0",
            recipient_email=f"queue-{marker}-0@example.com",
            subject="existing",
            body="existing",
            status="pending",
            scheduled_at=now,
        ))
        db.commit()

    response = client.post(f"/api/local/email-auto/campaigns/{campaign_id}/generate-jobs?limit=1")

    assert response.status_code == 200
    assert response.json()["created_jobs"] == 2
    with SessionLocal() as db:
        total = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id)
        )
    assert total == 3


def test_campaign_queue_is_created_only_when_window_starts(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_window_{marker}"
    before_window = datetime(2026, 6, 4, 8, 0, 0)
    in_window = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: in_window)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Window Queue {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=2,
            hourly_limit=2,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index in range(2):
            db.add(Creator(
                id=f"creator_window_{marker}_{index}",
                platform="queue_window_test",
                department_code="cross_border",
                handle=f"queue_window_{marker}_{index}",
                email=f"queue-window-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=in_window,
                collected_at=in_window,
            ))
        db.commit()

        before_summary = email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=before_window)
        before_total = db.scalar(select(func.count()).select_from(EmailAutoJob).where(EmailAutoJob.campaign_id == campaign_id))
        assert before_summary["created"] == 0
        assert before_total == 0

        email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=in_window)
        window_key = email_auto._campaign_window_key(campaign, in_window)
        total = db.scalar(select(func.count()).select_from(EmailAutoJob).where(EmailAutoJob.campaign_id == campaign_id))
        keyed_total = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.queue_window_key == window_key)
        )

    assert total == 2
    assert keyed_total == 2


def test_campaign_queue_clears_pending_when_window_ends(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_clear_{marker}"
    in_window = datetime(2026, 6, 4, 10, 0, 0)
    after_window = datetime(2026, 6, 4, 19, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: after_window)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Clear Queue {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=3,
            hourly_limit=3,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        db.flush()
        window_key = email_auto._campaign_window_key(campaign, in_window)
        campaign.queue_window_key = window_key
        for index, status in enumerate(["pending", "pending", "sent"]):
            creator_id = f"creator_clear_{marker}_{index}"
            db.add(Creator(
                id=creator_id,
                platform="queue_clear_test",
                department_code="cross_border",
                handle=f"queue_clear_{marker}_{index}",
                email=f"queue-clear-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=in_window,
                collected_at=in_window,
            ))
            db.add(EmailAutoJob(
                id=f"job_clear_{marker}_{index}",
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_id,
                recipient_email=f"queue-clear-{marker}-{index}@example.com",
                subject="subject",
                body="body",
                status=status,
                scheduled_at=in_window,
                queue_window_key=window_key,
            ))
        db.commit()

        email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=after_window)
        pending = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.status == "pending")
        )
        sent = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.status == "sent")
        )
        db.refresh(campaign)
        cleared_window_key = campaign.queue_cleared_window_key

    assert pending == 0
    assert sent == 1
    assert cleared_window_key == window_key


def test_stopped_campaign_pending_queue_is_cleared(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_stopped_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Stopped Queue {marker}",
            status="paused",
            start_time="09:30",
            end_time="18:00",
            daily_limit=2,
            hourly_limit=2,
            interval_min_seconds=30,
            interval_max_seconds=30,
            queue_window_key="202606040930-202606041800",
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index, status in enumerate(["pending", "sent"]):
            creator_id = f"creator_stopped_{marker}_{index}"
            db.add(Creator(
                id=creator_id,
                platform="queue_stopped_test",
                department_code="cross_border",
                handle=f"queue_stopped_{marker}_{index}",
                email=f"queue-stopped-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
            db.add(EmailAutoJob(
                id=f"job_stopped_{marker}_{index}",
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_id,
                recipient_email=f"queue-stopped-{marker}-{index}@example.com",
                subject="subject",
                body="body",
                status=status,
                scheduled_at=now,
                queue_window_key=campaign.queue_window_key,
            ))
        db.commit()

        email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=now)
        pending = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.status == "pending")
        )
        sent = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.status == "sent")
        )
        db.refresh(campaign)
        cleared_window_key = campaign.queue_cleared_window_key

    assert pending == 0
    assert sent == 1
    assert cleared_window_key == "202606040930-202606041800"


def test_generate_jobs_expands_candidates_to_reach_campaign_daily_limit(client, monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_expand_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)
    filters = {**email_auto.DEFAULT_FILTERS, "keyword": f"strict_{marker}"}

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Expand Queue {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=3,
            hourly_limit=3,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(filters),
        )
        db.add(campaign)
        for index in range(3):
            handle = f"strict_{marker}" if index == 0 else f"expanded_{marker}_{index}"
            db.add(Creator(
                id=f"creator_expand_{marker}_{index}",
                platform="queue_expand_test",
                department_code="cross_border",
                handle=handle,
                email=f"queue-expand-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.commit()

    response = client.post(f"/api/local/email-auto/campaigns/{campaign_id}/generate-jobs")

    assert response.status_code == 200
    assert response.json()["created_jobs"] == 3
    with SessionLocal() as db:
        total = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id)
        )
    assert total == 3


def test_campaign_queue_uses_rolling_batch_for_large_total(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_roll_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Rolling Queue {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=300,
            hourly_limit=300,
            interval_min_seconds=90,
            interval_max_seconds=240,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index in range(80):
            db.add(Creator(
                id=f"creator_roll_{marker}_{index}",
                platform="rolling_queue_test",
                department_code="cross_border",
                handle=f"rolling_queue_{marker}_{index}",
                email=f"rolling-queue-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.commit()

        target = email_auto._rolling_queue_target(db, campaign)
        summary = email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=now)
        total = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id)
        )

    assert summary["created"] == target
    assert total == target
    assert total < 300


def test_campaign_total_limit_stops_generation_after_completed_jobs(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_done_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    old_sent = now - timedelta(days=3)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Completed Total {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=2,
            hourly_limit=2,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index in range(6):
            creator_id = f"creator_done_{marker}_{index}"
            db.add(Creator(
                id=creator_id,
                platform="completed_total_test",
                department_code="cross_border",
                handle=f"completed_total_{marker}_{index}",
                email=f"completed-total-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
            if index < 2:
                db.add(EmailAutoJob(
                    id=f"job_done_{marker}_{index}",
                    department_code="cross_border",
                    campaign_id=campaign_id,
                    creator_id=creator_id,
                    recipient_email=f"completed-total-{marker}-{index}@example.com",
                    subject="sent",
                    body="sent",
                    status="sent",
                    scheduled_at=old_sent,
                    sent_at=old_sent,
                    updated_at=old_sent,
                ))
            elif index == 2:
                db.add(EmailAutoJob(
                    id=f"job_done_pending_{marker}",
                    department_code="cross_border",
                    campaign_id=campaign_id,
                    creator_id=creator_id,
                    recipient_email=f"completed-total-{marker}-{index}@example.com",
                    subject="pending",
                    body="pending",
                    status="pending",
                    scheduled_at=now,
                    queue_window_key=email_auto._campaign_window_key(campaign, now),
                ))
        db.commit()

        summary = email_auto.maintain_email_auto_campaign_queues(db, department_code="cross_border", now=now)
        pending = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id, EmailAutoJob.status == "pending")
        )
        completed = email_auto._campaign_completed_job_count(db, campaign)

    assert summary["created"] == 0
    assert pending == 0
    assert completed == 2


def test_update_campaign_daily_limit_auto_backfills_queue(client, monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_update_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Auto Backfill {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=1,
            hourly_limit=1,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        db.add(campaign)
        for index in range(3):
            creator_id = f"creator_update_{marker}_{index}"
            db.add(Creator(
                id=creator_id,
                platform="queue_update_test",
                department_code="cross_border",
                handle=f"queue_update_{marker}_{index}",
                email=f"queue-update-{marker}-{index}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.add(EmailAutoJob(
            id=f"existing_update_job_{marker}",
            department_code="cross_border",
            campaign_id=campaign_id,
            creator_id=f"creator_update_{marker}_0",
            recipient_email=f"queue-update-{marker}-0@example.com",
            subject="existing",
            body="existing",
            status="pending",
            scheduled_at=now,
        ))
        db.commit()

    payload = {
        "name": f"Auto Backfill {marker}",
        "status": "running",
        "schedule_type": "daily",
        "weekdays": [],
        "month_days": [1],
        "start_time": "09:30",
        "end_time": "18:00",
        "daily_limit": 3,
        "hourly_limit": 3,
        "interval_min_seconds": 30,
        "interval_max_seconds": 30,
        "mailbox_pool": "all",
        "send_mode": "send",
        "filters": email_auto.DEFAULT_FILTERS,
        "generate_jobs": False,
        "candidate_limit": 1,
    }

    response = client.patch(f"/api/local/email-auto/campaigns/{campaign_id}", json=payload)

    assert response.status_code == 200
    assert response.json()["created_jobs"] == 2
    with SessionLocal() as db:
        total = db.scalar(
            select(func.count())
            .select_from(EmailAutoJob)
            .where(EmailAutoJob.campaign_id == campaign_id)
        )
    assert total == 3


def test_cancel_campaign_skips_pending_jobs_and_keeps_sent_history(client):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_cancel_campaign_{marker}"
    pending_id = f"job_cancel_campaign_pending_{marker}"
    sent_id = f"job_cancel_campaign_sent_{marker}"
    creator_pending_id = f"creator_cancel_campaign_pending_{marker}"
    creator_sent_id = f"creator_cancel_campaign_sent_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)

    with SessionLocal() as db:
        db.add(EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Cancel Campaign {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=2,
            hourly_limit=2,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        ))
        for creator_id, handle in [(creator_pending_id, "pending"), (creator_sent_id, "sent")]:
            db.add(Creator(
                id=creator_id,
                platform="cancel_campaign_test",
                department_code="cross_border",
                handle=f"cancel_campaign_{handle}_{marker}",
                email=f"cancel-campaign-{handle}-{marker}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.add_all([
            EmailAutoJob(
                id=pending_id,
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_pending_id,
                recipient_email=f"cancel-campaign-pending-{marker}@example.com",
                subject="pending",
                body="pending",
                status="pending",
                scheduled_at=now,
            ),
            EmailAutoJob(
                id=sent_id,
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_sent_id,
                recipient_email=f"cancel-campaign-sent-{marker}@example.com",
                subject="sent",
                body="sent",
                status="sent",
                scheduled_at=now,
                sent_at=now,
            ),
        ])
        db.commit()

    response = client.patch(f"/api/local/email-auto/campaigns/{campaign_id}/status", json={"status": "cancelled"})

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["status"] == "cancelled"
    assert body["skipped_jobs"] == 1
    with SessionLocal() as db:
        campaign = db.get(EmailAutoCampaign, campaign_id)
        pending = db.get(EmailAutoJob, pending_id)
        sent = db.get(EmailAutoJob, sent_id)
    assert campaign.status == "cancelled"
    assert pending.status == "skipped"
    assert pending.failure_reason == "计划已取消"
    assert sent.status == "sent"


def test_delete_campaign_hides_plan_and_clears_visible_queue(client, monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_delete_campaign_{marker}"
    pending_id = f"job_delete_campaign_pending_{marker}"
    sent_id = f"job_delete_campaign_sent_{marker}"
    creator_pending_id = f"creator_delete_campaign_pending_{marker}"
    creator_sent_id = f"creator_delete_campaign_sent_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    before_sent = client.get("/api/local/email-auto/dashboard").json()["dashboard"]["today_sent"]
    with SessionLocal() as db:
        db.add(EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Delete Campaign {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=2,
            hourly_limit=2,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        ))
        for creator_id, handle in [(creator_pending_id, "pending"), (creator_sent_id, "sent")]:
            db.add(Creator(
                id=creator_id,
                platform="delete_campaign_test",
                department_code="cross_border",
                handle=f"delete_campaign_{handle}_{marker}",
                email=f"delete-campaign-{handle}-{marker}@example.com",
                has_email=1,
                recommendation_score=90,
                review_required=0,
                recommended_at=now,
                collected_at=now,
            ))
        db.add_all([
            EmailAutoJob(
                id=pending_id,
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_pending_id,
                recipient_email=f"delete-campaign-pending-{marker}@example.com",
                subject="pending",
                body="pending",
                status="pending",
                scheduled_at=now,
                updated_at=now,
            ),
            EmailAutoJob(
                id=sent_id,
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_sent_id,
                recipient_email=f"delete-campaign-sent-{marker}@example.com",
                subject="sent",
                body="sent",
                status="sent",
                scheduled_at=now,
                sent_at=now,
                updated_at=now,
            ),
        ])
        db.commit()

    response = client.delete(f"/api/local/email-auto/campaigns/{campaign_id}")

    assert response.status_code == 200
    assert response.json()["removed"] is True
    assert response.json()["skipped_jobs"] == 1
    with SessionLocal() as db:
        campaign = db.get(EmailAutoCampaign, campaign_id)
        pending = db.get(EmailAutoJob, pending_id)
        sent = db.get(EmailAutoJob, sent_id)
    assert campaign.status == "deleted"
    assert pending.status == "skipped"
    assert pending.failure_reason == "计划已删除"
    assert sent.status == "sent"

    dashboard = client.get("/api/local/email-auto/dashboard", params={"job_status": "all", "limit_jobs": 500}).json()
    assert all(item["id"] != campaign_id for item in dashboard["campaigns"])
    assert all(item["id"] not in {pending_id, sent_id} for item in dashboard["jobs"])
    assert dashboard["dashboard"]["today_sent"] == before_sent + 1


def test_cancel_job_marks_pending_job_skipped(client):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_cancel_{marker}"
    creator_id = f"creator_cancel_{marker}"
    job_id = f"job_cancel_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)

    with SessionLocal() as db:
        db.add(EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Cancel Test {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=1,
            hourly_limit=1,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        ))
        db.add(Creator(
            id=creator_id,
            platform="cancel_test",
            department_code="cross_border",
            handle=f"cancel_{marker}",
            email=f"cancel-{marker}@example.com",
            has_email=1,
            recommendation_score=90,
            review_required=0,
            recommended_at=now,
            collected_at=now,
        ))
        db.add(EmailAutoJob(
            id=job_id,
            department_code="cross_border",
            campaign_id=campaign_id,
            creator_id=creator_id,
            recipient_email=f"cancel-{marker}@example.com",
            subject="cancel",
            body="cancel",
            status="pending",
            scheduled_at=now,
        ))
        db.commit()

    response = client.post(f"/api/local/email-auto/jobs/{job_id}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["item"]["status"] == "skipped"
    assert body["item"]["reason"] == "手动取消"
    with SessionLocal() as db:
        row = db.get(EmailAutoJob, job_id)
    assert row.status == "skipped"
    assert row.failure_reason == "手动取消"


def test_dashboard_sent_stat_uses_rolling_24_hour_window(client, monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_dashboard_{marker}"
    creator_id = f"creator_dashboard_{marker}"
    now = datetime(2026, 6, 4, 12, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    before = client.get("/api/local/email-auto/dashboard").json()["dashboard"]["today_sent"]
    with SessionLocal() as db:
        db.add(EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Dashboard Window {marker}",
            status="paused",
            start_time="09:30",
            end_time="18:00",
            daily_limit=10,
            hourly_limit=10,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        ))
        db.add(Creator(
            id=creator_id,
            platform="dashboard_window_test",
            department_code="cross_border",
            handle=f"dashboard_window_{marker}",
            email=f"dashboard-window-{marker}@example.com",
            has_email=1,
            recommendation_score=90,
            review_required=0,
            recommended_at=now,
            collected_at=now,
        ))
        db.add_all([
            EmailAutoJob(
                id=f"recent_dashboard_job_{marker}",
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_id,
                recipient_email=f"recent-dashboard-{marker}@example.com",
                subject="recent",
                body="recent",
                status="sent",
                scheduled_at=now - timedelta(hours=23, minutes=59),
                updated_at=now - timedelta(hours=23, minutes=59),
            ),
            EmailAutoJob(
                id=f"old_dashboard_job_{marker}",
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_id,
                recipient_email=f"old-dashboard-{marker}@example.com",
                subject="old",
                body="old",
                status="draft_created",
                scheduled_at=now - timedelta(hours=24, minutes=1),
                updated_at=now - timedelta(hours=24, minutes=1),
            ),
        ])
        db.commit()

    after = client.get("/api/local/email-auto/dashboard").json()["dashboard"]["today_sent"]

    assert after == before + 1


def test_campaign_total_limit_blocks_after_completed_total(monkeypatch):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_daily_window_{marker}"
    creator_id = f"creator_daily_window_{marker}"
    now = datetime(2026, 6, 4, 10, 0, 0)
    monkeypatch.setattr(email_auto, "_now", lambda: now)

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Daily Window {marker}",
            status="running",
            start_time="09:30",
            end_time="18:00",
            daily_limit=1,
            hourly_limit=10,
            interval_min_seconds=30,
            interval_max_seconds=30,
            filters_json=email_auto._json_dumps(email_auto.DEFAULT_FILTERS),
        )
        creator = Creator(
            id=creator_id,
            platform="daily_window_test",
            department_code="cross_border",
            handle=f"daily_window_{marker}",
            email=f"daily-window-{marker}@example.com",
            has_email=1,
            recommendation_score=90,
            review_required=0,
            recommended_at=now,
            collected_at=now,
        )
        pending = EmailAutoJob(
            id=f"pending_daily_window_{marker}",
            department_code="cross_border",
            campaign_id=campaign_id,
            creator_id=creator_id,
            recipient_email=f"pending-daily-window-{marker}@example.com",
            subject="pending",
            body="pending",
            status="pending",
            scheduled_at=now,
        )
        db.add_all([
            campaign,
            creator,
            EmailAutoJob(
                id=f"recent_daily_window_{marker}",
                department_code="cross_border",
                campaign_id=campaign_id,
                creator_id=creator_id,
                recipient_email=f"recent-daily-window-{marker}@example.com",
                subject="recent",
                body="recent",
                status="sent",
                scheduled_at=now - timedelta(hours=23, minutes=59),
                updated_at=now - timedelta(hours=23, minutes=59),
            ),
            pending,
        ])
        db.commit()

        result = email_auto._process_one_job(db, pending, {"id": "test"})

    assert result["reason"] == "计划总任务量已完成"
