from __future__ import annotations

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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
    # 明确退订先进入待人工确认，避免规则误判后直接永久禁止联系。
    do_not_contact_status: Mapped[str] = mapped_column(String(40), default="none", index=True)
    do_not_contact_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_contact_requested_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    owner_bd: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_product_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    recommended_collab_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DoNotContactConfirmation(Base):
    """DNC 审核流水：保存待确认和已决议记录，供后续采集与建联拦截审计。"""

    __tablename__ = "do_not_contact_confirmations"
    __table_args__ = (Index("ix_dnc_confirmations_creator_status", "creator_id", "status"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(80), default="explicit_opt_out")
    status: Mapped[str] = mapped_column(String(40), default="pending_confirmation")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Product(Base):
    """产品档案：按产品类型为达人回复建议提供可控的业务上下文。"""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("product_type", name="uq_products_product_type"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_type: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    selling_points_json: Mapped[str] = mapped_column(Text, default="[]")
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    collaboration_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    forbidden_claims_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class InboundReply(Base):
    """入站回复表：独立 MVP 中承接原项目 creator_email_messages 的 inbound 角色。"""

    __tablename__ = "inbound_replies"
    __table_args__ = (
        UniqueConstraint(
            "department_code",
            "channel",
            "external_message_id",
            name="uq_inbound_replies_external_message",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", index=True)
    # simulation 仅用于 MVP 演练；真实渠道需提供上游稳定消息 ID。
    channel: Mapped[str] = mapped_column(String(40), default="simulation", index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    from_email: Mapped[str] = mapped_column(String(320), default="")
    to_email: Mapped[str] = mapped_column(String(1000), default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(10), default="plain")
    message_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 处理状态表示流程进度，规则分类表示达人意图，两者分开便于后续扩展状态机。
    processing_status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    reply_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
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
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
