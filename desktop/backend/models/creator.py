from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class Creator(Base):
    """Master creator profile — one row per (platform, handle)."""

    __tablename__ = "creators"
    __table_args__ = (UniqueConstraint("platform", "handle", name="uq_creator_platform_handle"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), default="tiktok", index=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    handle: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    followers_raw: Mapped[str | None] = mapped_column(String(40), nullable=True)
    followers_count: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    has_email: Mapped[int] = mapped_column(Integer, default=0, index=True)
    external_links_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_video_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_video_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)

    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    # ---- Scoring fields ----
    priority_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    fit_level: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    priority_level: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    queue_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)

    primary_product_category: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    primary_product_fit_score: Mapped[int] = mapped_column(Integer, default=0)
    feminine_care_fit: Mapped[int] = mapped_column(Integer, default=0)
    pet_care_fit: Mapped[int] = mapped_column(Integer, default=0)
    home_care_fit: Mapped[int] = mapped_column(Integer, default=0)
    adult_care_fit: Mapped[int] = mapped_column(Integer, default=0)
    mom_baby_fit: Mapped[int] = mapped_column(Integer, default=0)
    health_mask_fit: Mapped[int] = mapped_column(Integer, default=0)

    data_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    contactability_score: Mapped[int] = mapped_column(Integer, default=0)  # used as gate, not main score
    content_format_score: Mapped[int] = mapped_column(Integer, default=0)
    commercial_value_score: Mapped[int] = mapped_column(Integer, default=0)
    follower_scale_score: Mapped[int] = mapped_column(Integer, default=0)
    audience_fit_score: Mapped[int] = mapped_column(Integer, default=0)

    # ---- Recommendation fields ----
    recommendation_status: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    current_status: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    store_assigned: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    owner_bd: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    recommended_product_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    recommended_collab_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    outreach_priority: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    recommendation_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_required: Mapped[int] = mapped_column(Integer, default=0, index=True)
    review_status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Evidence ----
    fit_evidence_source_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_strength: Mapped[str | None] = mapped_column(String(20), nullable=True)
    evidence_text_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    positive_tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    score_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tag_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rec_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scored_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    tagged_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    recommended_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
