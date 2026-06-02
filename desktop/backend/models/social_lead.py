"""Xiaohongshu (XHS) / Douyin social-media lead models.

Native port of the standalone xhs_cleaning schema into x9db. Postgres-specific
features (triggers, gin/trgm indexes, jsonb, views, the dedicated `xhs_clean`
schema) are dropped in favour of portable SQLAlchemy columns so the same models
run on both SQLite (dev) and PostgreSQL (prod). Table names are prefixed `xhs_`
to live alongside the recruitment + creator tables in the default schema.

Every table carries `department_code` for X9 multi-department scoping and a
`raw_json` / payload catch-all so the Phase 3 ingest/cleaning pipeline can land
the full snapshot without further migrations.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


def _uid() -> str:
    return uuid.uuid4().hex


class XhsCollectionRun(Base):
    """One collection batch fired from the browser extension (xhs / douyin)."""

    __tablename__ = "xhs_collection_runs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    run_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    source_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    plugin_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    collector_version: Mapped[str | None] = mapped_column(String(60), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)
    raw_settings: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class XhsRawSnapshot(Base):
    """Append-only raw JSON payload uploaded by the extension (audit trail)."""

    __tablename__ = "xhs_raw_snapshots"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    snapshot_type: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    clean_status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    observed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsUser(Base):
    """Cleaned social-media profile (potential cross-border buyer / partner)."""

    __tablename__ = "xhs_users"
    __table_args__ = (
        UniqueConstraint("platform", "external_user_id", name="uq_xhs_user_platform_external"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    external_user_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    xhs_user_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    username_clean: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    account_clean: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    canonical_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    follower_count: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    following_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    liked_collect_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    has_contact: Mapped[int] = mapped_column(Integer, default=0, index=True)
    contact_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    clean_status: Mapped[str] = mapped_column(String(20), default="cleaned", index=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class XhsNote(Base):
    """Cleaned note (xhs) / video (douyin)."""

    __tablename__ = "xhs_notes"
    __table_args__ = (
        UniqueConstraint("platform", "external_post_id", name="uq_xhs_note_platform_external"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    external_post_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    xhs_note_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    canonical_note_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    publish_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    collect_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    author_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class XhsComment(Base):
    """Cleaned comment / reply under a note."""

    __tablename__ = "xhs_comments"
    __table_args__ = (
        UniqueConstraint("platform", "external_comment_id", name="uq_xhs_comment_platform_external"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    external_comment_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    xhs_comment_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    note_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    content_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsExtractedContact(Base):
    """Contact (email / phone / wechat / url) extracted from a user or comment."""

    __tablename__ = "xhs_extracted_contacts"
    __table_args__ = (
        UniqueConstraint(
            "owner_type", "owner_id", "contact_type", "value_norm",
            name="uq_xhs_contact_owner_value",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    owner_type: Mapped[str] = mapped_column(String(20), index=True)
    owner_id: Mapped[str] = mapped_column(String(120), index=True)
    user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    contact_type: Mapped[str] = mapped_column(String(30), index=True)
    value_raw: Mapped[str] = mapped_column(Text)
    value_norm: Mapped[str] = mapped_column(String(400), index=True)
    source_field: Mapped[str | None] = mapped_column(String(60), nullable=True)
    rule_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsAiJudgment(Base):
    """GPT purchase-intent / fit judgment for a social-media user."""

    __tablename__ = "xhs_ai_judgments"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    fit_score: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    fit_level: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    intent_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    judgment: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
