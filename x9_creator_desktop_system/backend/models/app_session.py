from __future__ import annotations

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class AppSession(Base):
    __tablename__ = "app_sessions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    gmail_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    entry_scope: Mapped[str] = mapped_column(String(40), default="workspace", index=True)
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[object] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
