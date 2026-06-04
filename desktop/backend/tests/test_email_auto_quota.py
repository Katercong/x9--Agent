from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from desktop.backend.database import SessionLocal
from desktop.backend.models.creator import Creator
from desktop.backend.models.email_auto import GmailAccountQuota
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
            synced_sent_date=now.date().isoformat(),
        )
        db.add(quota)
        db.commit()

        assert email_auto._daily_auto_sent(db, email, quota) == 1

        quota.synced_sent_date = email_auto._quota_window_key()
        db.commit()

        assert email_auto._daily_auto_sent(db, email, quota) == 7
