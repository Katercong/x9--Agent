from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class FollowupTask(Base):
    """Task queue for outreach follow-up work."""

    __tablename__ = "followup_tasks"
    __table_args__ = (
        Index("ix_followup_tasks_department_status_due", "department_code", "status", "due_at"),
        Index("ix_followup_tasks_creator_status", "creator_id", "status"),
        Index("ix_followup_tasks_owner_status_due", "owner_user_id", "status", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    due_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
