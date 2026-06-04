from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class EmailAutoCampaign(Base):
    __tablename__ = "email_auto_campaigns"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="paused", index=True)
    schedule_type: Mapped[str] = mapped_column(String(20), default="daily")
    weekdays_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    month_days_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[str] = mapped_column(String(10), default="09:30")
    end_time: Mapped[str] = mapped_column(String(10), default="18:00")
    daily_limit: Mapped[int] = mapped_column(Integer, default=100)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=20)
    interval_min_seconds: Mapped[int] = mapped_column(Integer, default=90)
    interval_max_seconds: Mapped[int] = mapped_column(Integer, default=240)
    mailbox_pool: Mapped[str] = mapped_column(String(80), default="all")
    send_mode: Mapped[str] = mapped_column(String(20), default="draft")
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue_window_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    queue_cleared_window_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class GmailAccountQuota(Base):
    __tablename__ = "gmail_account_quotas"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    account_id: Mapped[str] = mapped_column(String(120), ForeignKey("gmail_accounts.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    daily_quota: Mapped[int] = mapped_column(Integer, default=40)
    synced_sent_today: Mapped[int] = mapped_column(Integer, default=0)
    synced_sent_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="normal", index=True)
    cooldown_until: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    last_sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class EmailAutoJob(Base):
    __tablename__ = "email_auto_jobs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    campaign_id: Mapped[str] = mapped_column(String(120), ForeignKey("email_auto_campaigns.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    gmail_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True)
    sender_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(10), default="html")
    product_asset_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    scheduled_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    outreach_email_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    filters_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue_window_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
