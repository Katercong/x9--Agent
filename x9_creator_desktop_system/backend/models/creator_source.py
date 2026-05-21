from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorSource(Base):
    """Processed acquisition/source fact for one creator.

    Raw observations remain append-only capture logs. This table records the
    processed business fact that a creator came from TikTok Shop, TikTok video,
    or BD data, optionally tied back to the raw observation and user/account
    that produced it.
    """

    __tablename__ = "creator_sources"
    __table_args__ = (
        Index("ix_creator_sources_creator_source", "creator_id", "source_type"),
        Index("ix_creator_sources_actor_source", "actor_user_id", "source_type"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    handle: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)

    actor_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    raw_observation_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    first_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    last_seen_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
