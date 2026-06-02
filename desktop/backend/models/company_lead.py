from __future__ import annotations

import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


def _uid() -> str:
    return uuid.uuid4().hex


class CompanyLead(Base):
    """Potential cross-border B2B partner (merchant / intermediary / logistics)
    discovered from recruitment sites. Ported from CompanyLeads/backend/models.py
    with a department_code column for X9 multi-department scoping."""

    __tablename__ = "company_leads"
    __table_args__ = (
        UniqueConstraint("platform", "platform_company_id", name="uq_company_platform_id"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(40), default="51job", index=True)
    platform_company_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    company_name: Mapped[str] = mapped_column(String(300), index=True)
    industry: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_range: Mapped[str | None] = mapped_column(String(60), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    company_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    us_market_flag: Mapped[int] = mapped_column(Integer, default=0, index=True)
    excluded: Mapped[int] = mapped_column(Integer, default=0, index=True)
    excluded_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    tier: Mapped[str | None] = mapped_column(String(4), index=True, nullable=True)
    cooperation_type: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    lead_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)

    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    hr_wechat: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_verified: Mapped[int] = mapped_column(Integer, default=0, index=True)

    raw_jd_titles: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_jd_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_status: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    llm_score_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_scored_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    source_mode: Mapped[str] = mapped_column(String(20), default="job_seeker", index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="public_job", index=True)
    permission_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    owner_bd: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CompanyObservation(Base):
    """Append-only audit trail of each scrape/extension push for a company lead."""

    __tablename__ = "company_observations"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    company_lead_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("company_leads.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(40), index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class CompanyOutreachEmail(Base):
    """BD ↔ company-lead email touch log."""

    __tablename__ = "company_outreach_emails"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    company_lead_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("company_leads.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reply_received: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
