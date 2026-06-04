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


def test_generate_jobs_fills_to_campaign_daily_limit_even_when_limit_is_smaller(client):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_{marker}"
    now = datetime.now()

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Queue Limit {marker}",
            status="running",
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


def test_update_campaign_daily_limit_auto_backfills_queue(client):
    marker = uuid.uuid4().hex
    campaign_id = f"eac_update_{marker}"
    now = datetime.now()

    with SessionLocal() as db:
        campaign = EmailAutoCampaign(
            id=campaign_id,
            department_code="cross_border",
            name=f"Auto Backfill {marker}",
            status="running",
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
