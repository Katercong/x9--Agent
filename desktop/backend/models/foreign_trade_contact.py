from __future__ import annotations

import uuid

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


def _uid() -> str:
    return uuid.uuid4().hex


class ForeignTradeContactRecord(Base):
    """Contact/follow-up state for foreign-trade customer and company leads."""

    __tablename__ = "foreign_trade_contact_records"
    __table_args__ = (
        UniqueConstraint("department_code", "lead_type", "lead_id", name="uq_ft_contact_lead"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True, default=_uid)
    department_code: Mapped[str] = mapped_column(String(40), default="foreign_trade", index=True)
    lead_type: Mapped[str] = mapped_column(String(30), index=True)
    lead_id: Mapped[str] = mapped_column(String(120), index=True)
    lead_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    account: Mapped[str | None] = mapped_column(String(220), nullable=True, index=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending_contact", index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opened_count: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_followup_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    next_followup_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    followup_result: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    followup_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
