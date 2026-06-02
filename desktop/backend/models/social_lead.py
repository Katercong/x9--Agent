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
    user_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    username: Mapped[str | None] = mapped_column(String(300), nullable=True)
    username_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    username_clean: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    account: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_clean: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    gender_text: Mapped[str | None] = mapped_column(String(60), nullable=True)
    followers_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    follower_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    follower_count: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    following_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    following_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    liked_collect_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    liked_collect_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    history_posts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    has_contact: Mapped[int] = mapped_column(Integer, default=0, index=True)
    contact_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_quality: Mapped[str | None] = mapped_column(Text, nullable=True)
    clean_status: Mapped[str] = mapped_column(String(20), default="cleaned", index=True)
    raw_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    profile_collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
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
    note_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    xhs_note_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_note_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_result_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    publish_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    like_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    collect_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    collect_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    comment_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    author_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    author_xhs_user_id_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author_username_snapshot: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    images_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    relevance_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
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
    comment_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    xhs_comment_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    note_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    note_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_comment_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    root_comment_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_comment_external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    user_xhs_id_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    username: Mapped[str | None] = mapped_column(String(300), nullable=True)
    username_snapshot: Mapped[str | None] = mapped_column(String(300), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    published_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    like_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_author_reply: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    data_quality: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    first_run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsNoteMedia(Base):
    """Media assets extracted from a note / Douyin video."""

    __tablename__ = "xhs_note_media"
    __table_args__ = (
        UniqueConstraint("note_id", "url", name="uq_xhs_note_media_note_url"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    note_id: Mapped[str] = mapped_column(String(120), index=True)
    media_type: Mapped[str] = mapped_column(String(20), default="image", index=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    raw_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsUserSource(Base):
    """Evidence linking a user to notes/comments/search keywords."""

    __tablename__ = "xhs_user_sources"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    note_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    comment_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_images: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_hash: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    observed_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class XhsUserHistoryPost(Base):
    """Historical posts collected from a user's profile page."""

    __tablename__ = "xhs_user_history_posts"
    __table_args__ = (
        UniqueConstraint("user_id", "xhs_note_id", name="uq_xhs_history_user_note"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(20), default="xhs", index=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    xhs_note_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    canonical_note_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    like_count_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    like_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_at_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    raw_snapshot_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    collected_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
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
