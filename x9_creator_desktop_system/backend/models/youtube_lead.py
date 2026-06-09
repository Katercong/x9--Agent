from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..utils.id_utils import new_id
from ..youtube_database import YoutubeBase


class YoutubeImportRun(YoutubeBase):
    __tablename__ = "youtube_import_runs"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: new_id("youtube_run"))
    department_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    filename: Mapped[str] = mapped_column(String(300), default="")
    keyword: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    source_search_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="imported", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    kept_rows: Mapped[int] = mapped_column(Integer, default=0)
    dropped_no_contact: Mapped[int] = mapped_column(Integer, default=0)
    inserted: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    sources_added: Mapped[int] = mapped_column(Integer, default=0)
    manual_review: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class YoutubeRawRow(YoutubeBase):
    __tablename__ = "youtube_raw_rows"

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: new_id("youtube_raw"))
    run_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("youtube_import_runs.id"), index=True, nullable=True)
    department_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    row_hash: Mapped[str] = mapped_column(String(80), index=True)
    source_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    channel_key: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    channel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)
    clean_status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    drop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class YoutubeLead(YoutubeBase):
    __tablename__ = "youtube_leads"
    __table_args__ = (
        UniqueConstraint("department_code", "channel_key", name="uq_youtube_leads_dept_channel_key"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: new_id("youtube_lead"))
    department_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    platform: Mapped[str] = mapped_column(String(40), default="youtube", index=True)
    channel_key: Mapped[str] = mapped_column(String(300), index=True)
    channel_id: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    channel_handle: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    channel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    emails_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_email: Mapped[int] = mapped_column(Integer, default=0, index=True)
    needs_manual_review: Mapped[int] = mapped_column(Integer, default=0, index=True)
    review_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_review_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_source_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    latest_video_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    latest_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_video_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_keyword: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    source_types_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class YoutubeLeadSource(YoutubeBase):
    __tablename__ = "youtube_lead_sources"
    __table_args__ = (
        UniqueConstraint("lead_id", "source_key", name="uq_youtube_lead_sources_lead_source_key"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=lambda: new_id("youtube_src"))
    department_code: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    lead_id: Mapped[str] = mapped_column(String(120), ForeignKey("youtube_leads.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("youtube_import_runs.id"), index=True, nullable=True)
    raw_row_id: Mapped[str | None] = mapped_column(String(120), ForeignKey("youtube_raw_rows.id"), index=True, nullable=True)
    source_key: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_review_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
