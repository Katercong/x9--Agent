from __future__ import annotations

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class ExtensionCommand(Base):
    """Commands queued for the chrome extension to execute.

    Flow:
        1. Dashboard or backend rule pushes a row (status=pending).
        2. Extension polls `/api/local/extension/commands/pending` per worker.
        3. Extension executes the command, then POSTs `/ack` with status
           `done` or `error` plus optional result payload.
    """

    __tablename__ = "extension_commands"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    worker_id: Mapped[str] = mapped_column(String(80), index=True)
    command_type: Mapped[str] = mapped_column(String(60), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | claimed | done | error | expired
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    claimed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
