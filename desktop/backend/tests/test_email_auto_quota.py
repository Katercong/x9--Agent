from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select

from desktop.backend.database import SessionLocal
from desktop.backend.models.creator import Creator
from desktop.backend.models.email_auto import EmailAutoCampaign, EmailAutoJob, GmailAccountQuota
from desktop.backend.models.gmail_account import GmailAccount
from desktop.backend.models.outreach_email import OutreachEmail
from desktop.backend.routers import email_auto


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
