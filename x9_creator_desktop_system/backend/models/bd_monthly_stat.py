from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class BdMonthlyStat(Base):
    """Migrated BD monthly summary from legacy staff.note JSON."""

    __tablename__ = "bd_monthly_stats"
    __table_args__ = (
        UniqueConstraint(
            "department_code",
            "owner_name",
            "month",
            "source_staff_id",
            name="uq_bd_monthly_stats_owner_month_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    owner_name: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    month: Mapped[str] = mapped_column(String(20), default="", index=True)
    contacted: Mapped[int] = mapped_column(Integer, default=0)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    videos: Mapped[int] = mapped_column(Integer, default=0)
    source_staff_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_note_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
