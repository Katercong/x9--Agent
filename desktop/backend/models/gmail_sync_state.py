from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class GmailSyncState(Base):
    """Per-Gmail-account inbox sync cursor and scheduling state."""

    __tablename__ = "gmail_sync_state"

    account_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("gmail_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    last_history_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_sync_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    next_sync_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(40), default="idle", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), index=True)
