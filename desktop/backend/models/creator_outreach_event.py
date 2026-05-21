from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorOutreachEvent(Base):
    """Append-only creator outreach lifecycle event."""

    __tablename__ = "creator_outreach_events"
    __table_args__ = (
        Index("ix_creator_outreach_events_creator_type", "creator_id", "event_type"),
        Index("ix_creator_outreach_events_actor_type", "actor_user_id", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_bd: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
