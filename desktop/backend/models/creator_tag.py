from __future__ import annotations

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorTag(Base):
    __tablename__ = "creator_tags"
    __table_args__ = (UniqueConstraint("creator_id", "tag_code", name="uq_creator_tag"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    tag_code: Mapped[str] = mapped_column(String(120), index=True)
    tag_type: Mapped[str] = mapped_column(String(40), index=True)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
