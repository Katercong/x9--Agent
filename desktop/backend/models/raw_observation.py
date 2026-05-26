from __future__ import annotations

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class RawObservation(Base):
    """Raw payload uploaded by the chrome extension. Append-only audit trail."""

    __tablename__ = "raw_observations"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    platform: Mapped[str] = mapped_column(String(40), default="tiktok", index=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    source: Mapped[str] = mapped_column(String(80), default="chrome_extension")
    actor_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    lead_status: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    process_status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    processed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    process_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(80), index=True)
    collected_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
