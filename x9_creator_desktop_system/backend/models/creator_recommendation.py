from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class CreatorRecommendation(Base):
    """History of recommendation runs — append a new row each time the
    recommendation engine emits a fresh decision."""

    __tablename__ = "creator_recommendations"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    source_type: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recommendation_status: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    recommended_product_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    recommended_collab_type: Mapped[str | None] = mapped_column(String(60), index=True, nullable=True)
    outreach_priority: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    recommendation_score: Mapped[int] = mapped_column(Integer, default=0)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    is_current: Mapped[int] = mapped_column(Integer, default=1, index=True)
    rec_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
