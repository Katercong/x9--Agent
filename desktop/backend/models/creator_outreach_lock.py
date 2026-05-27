from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorOutreachLock(Base):
    """Short-lived operation lock for one creator's email outreach."""

    __tablename__ = "creator_outreach_locks"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(120), index=True)
    owner_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    heartbeat_count: Mapped[int] = mapped_column(Integer, default=0)
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[object] = mapped_column(DateTime, index=True)
    released_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
