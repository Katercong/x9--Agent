from __future__ import annotations

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class ExtensionSession(Base):
    """One row per extension worker — last heartbeat wins."""

    __tablename__ = "extension_sessions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    extension_id: Mapped[str] = mapped_column(String(120), index=True)
    extension_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    worker_id: Mapped[str] = mapped_column(String(80), index=True)
    account_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    browser_profile: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="online", index=True)
    current_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_type: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    tiktok_page_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tiktok_login_status: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    active_tab_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_heartbeat_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
