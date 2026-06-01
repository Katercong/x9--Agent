from __future__ import annotations

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorEmailMessage(Base):
    """A Gmail message captured for a creator outreach conversation."""

    __tablename__ = "creator_email_messages"
    __table_args__ = (
        UniqueConstraint(
            "gmail_account_id",
            "gmail_message_id",
            name="uq_creator_email_messages_account_message",
        ),
        Index("ix_creator_email_messages_creator_at", "creator_id", "message_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    outreach_email_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    gmail_account_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    gmail_account_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(120), index=True)

    direction: Mapped[str] = mapped_column(String(20), index=True)  # inbound | bounce
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    to_email: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_format: Mapped[str | None] = mapped_column(String(10), nullable=True)

    message_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
