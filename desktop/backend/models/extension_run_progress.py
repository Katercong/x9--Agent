from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class ExtensionRunProgress(Base):
    """Latest auto-run progress snapshot per worker.

    The extension pushes a row each time the run state changes
    (start, every step, stop). Older snapshots are not kept; this is the
    *current* state, suitable for "live progress" rendering on the
    dashboard.
    """

    __tablename__ = "extension_run_progress"
    __table_args__ = (UniqueConstraint("worker_id", name="uq_extension_run_progress_worker"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    worker_id: Mapped[str] = mapped_column(String(80), index=True)
    keyword: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # idle | starting | ensure_search | scanning | scrolling |
    # opening_profile | collecting_profile | resting | finished | error
    step: Mapped[str] = mapped_column(String(40), default="idle", index=True)
    running: Mapped[int] = mapped_column(Integer, default=0)
    stop_requested: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    profiles_visited: Mapped[int] = mapped_column(Integer, default=0)
    profiles_remaining: Mapped[int] = mapped_column(Integer, default=0)
    queue_size: Mapped[int] = mapped_column(Integer, default=0)
    leads_saved: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    scrolls_done: Mapped[int] = mapped_column(Integer, default=0)
    rest_breaks: Mapped[int] = mapped_column(Integer, default=0)

    current_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    current_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    settings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    queue_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recent_leads_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
