from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


def _uid() -> str:
    return uuid.uuid4().hex


class TalentLead(Base):
    """Cross-border talent (sales / e-commerce ops / overseas warehouse / supply
    chain / brand sales, US region preferred) discovered from recruitment sites.
    Ported from CompanyLeads/backend/models.py with a department_code column."""

    __tablename__ = "talent_leads"
    __table_args__ = (
        UniqueConstraint("platform", "platform_resume_id", name="uq_talent_platform_resume"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(40), default="qzrc", index=True)
    platform_resume_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    name_masked: Mapped[str | None] = mapped_column(String(120), nullable=True)
    desired_title: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    experience: Mapped[str | None] = mapped_column(String(100), nullable=True)
    education: Mapped[str | None] = mapped_column(String(100), nullable=True)
    major: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary_expectation: Mapped[str | None] = mapped_column(String(120), nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    wechat: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="authorized_import", index=True)
    consent_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    permission_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    tier: Mapped[str | None] = mapped_column(String(4), index=True, nullable=True)
    cooperation_type: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    lead_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_quality: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    next_action: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    search_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_status: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    llm_score_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    llm_score_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_score_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_scored_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    first_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
