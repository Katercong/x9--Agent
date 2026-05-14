from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class GmailAccount(Base):
    """A Gmail account that has been authorized to send outreach.

    Multiple BD members can each connect their own Gmail; outreach drafts
    pick which account to send from. Tokens (access + refresh) are stored
    per-account as JSON. Email is unique across the table.
    """

    __tablename__ = "gmail_accounts"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Full google.oauth2.credentials JSON dump
    token_json: Mapped[str] = mapped_column(Text)

    is_default: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1, index=True)

    last_used_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
