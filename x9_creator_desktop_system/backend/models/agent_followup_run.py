from __future__ import annotations

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database.connection import Base


class AgentFollowupRun(Base):
    """达人回复后，每一次 Follow-up Agent 分析与建议的留痕记录。"""

    __tablename__ = "agent_followup_runs"
    __table_args__ = (
        Index("ix_agent_followup_runs_creator_message", "creator_id", "inbound_message_id"),
        Index("ix_agent_followup_runs_department_created", "department_code", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)

    # 关联本次回复和达人，后续模块会用它回放上下文。
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    inbound_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    # 规则分类、建议状态和 LLM 调用状态都只表示 agent 建议，不直接改业务终态。
    reply_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    suggested_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    llm_status: Mapped[str] = mapped_column(String(40), default="not_configured", index=True)

    # JSON 先用 Text 存，保持 SQLite / PostgreSQL 都能直接跑 MVP。
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
