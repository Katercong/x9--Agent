from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Creator(Base):
    """达人主表：保存达人基础档案和当前跟进状态。"""

    __tablename__ = "creators"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    platform: Mapped[str] = mapped_column(String(40), default="tiktok", index=True)
    handle: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    followers_count: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    current_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    owner_bd: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_product_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recommended_collab_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class InboundReply(Base):
    """入站回复表：独立 MVP 中承接原项目 creator_email_messages 的 inbound 角色。"""

    __tablename__ = "inbound_replies"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", index=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    to_email: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(10), default="plain")
    message_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class OutreachEmail(Base):
    """历史建联邮件表：用于让 Agent 知道之前发过什么。"""

    __tablename__ = "outreach_emails"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    to_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="sent", index=True)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CreatorOutreachEvent(Base):
    """达人建联事件流水表。"""

    __tablename__ = "creator_outreach_events"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class FollowupTask(Base):
    """人工跟进待办表。"""

    __tablename__ = "followup_tasks"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    task_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=50)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentFollowupRun(Base):
    """Agent 运行留痕表。"""

    __tablename__ = "agent_followup_runs"
    __table_args__ = (
        Index("ix_agent_followup_runs_creator_reply", "creator_id", "inbound_reply_id"),
        Index("ix_agent_followup_runs_department_created", "department_code", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), index=True)
    inbound_reply_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    reply_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    suggested_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    llm_status: Mapped[str] = mapped_column(String(40), default="not_configured", index=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
