from __future__ import annotations

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class AuthUser(Base):
    """ReplyChat 内部身份映射；外部身份只以 source + subject 唯一标识。"""

    __tablename__ = "auth_users"
    __table_args__ = (
        UniqueConstraint("identity_source", "external_subject", name="uq_auth_users_identity_source_subject"),
        Index("ix_auth_users_identity_source_active", "identity_source", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    identity_source: Mapped[str] = mapped_column(String(40), nullable=False)
    external_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Department(Base):
    """授权目录中的部门；现有业务表仍以 department_code 作为归属字段。"""

    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserDepartmentMembership(Base):
    """用户在单个部门中的 Agent 角色；角色不具有跨部门隐式继承。"""

    __tablename__ = "user_department_memberships"
    __table_args__ = (
        UniqueConstraint("auth_user_id", "department_id", name="uq_user_department_memberships_user_department"),
        CheckConstraint("role IN ('operator', 'reviewer', 'admin')", name="ck_user_department_memberships_role"),
        Index("ix_user_department_memberships_user_active", "auth_user_id", "is_active"),
        Index("ix_user_department_memberships_department_active_role", "department_id", "is_active", "role"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    auth_user_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    authorization_source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    granted_by_auth_user_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AuthorizationAuditEvent(Base):
    """授权目录变更的追加式审计记录，不删除或覆盖既有事件。"""

    __tablename__ = "authorization_audit_events"
    __table_args__ = (
        Index("ix_authorization_audit_events_actor_created", "actor_auth_user_id", "created_at"),
        Index("ix_authorization_audit_events_target_created", "target_auth_user_id", "created_at"),
        Index("ix_authorization_audit_events_department_created", "department_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_auth_user_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    target_auth_user_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


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
    __table_args__ = (
        Index("ix_dnc_confirmations_creator_status", "creator_id", "status"),
        Index(
            "ix_dnc_confirmations_review_queue_creator_created",
            "creator_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id"), index=True)
    reason: Mapped[str] = mapped_column(String(80), default="explicit_opt_out")
    status: Mapped[str] = mapped_column(String(40), default="pending_confirmation")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class DeclineConfirmation(Base):
    """人工确认明确拒绝的不可变审计记录；不依赖也不伪造 Agent run。"""

    __tablename__ = "decline_confirmations"
    __table_args__ = (
        UniqueConstraint("inbound_reply_id", name="uq_decline_confirmations_reply"),
        Index("ix_decline_confirmations_department_confirmed", "department_code", "confirmed_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inbound_reply_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("inbound_replies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    confirmed_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


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
    campaign_timeline: Mapped[str | None] = mapped_column(Text, nullable=True)
    campaign_deliverables: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    forbidden_claims_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ReferenceMaterial(Base):
    """可版本化的合作参考资料，供提示词使用并保留运营更新历史。"""

    __tablename__ = "reference_materials"
    __table_args__ = (
        UniqueConstraint("reference_key", "version", name="uq_reference_material_version"),
        Index("ix_reference_materials_active_scope_product", "is_active", "scope", "product_type"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    reference_key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(40), index=True)
    material_type: Mapped[str] = mapped_column(String(60), index=True)
    product_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
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
        Index(
            "ix_inbound_replies_review_queue_status_created",
            "processing_status",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_inbound_replies_review_queue_department_status_created",
            "department_code",
            "processing_status",
            text("created_at DESC"),
            text("id DESC"),
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", index=True)
    # simulation 使用由消息内容导出的可重放 ID；真实渠道必须提供上游稳定消息 ID。
    channel: Mapped[str] = mapped_column(String(40), default="simulation", index=True)
    external_message_id: Mapped[str] = mapped_column(String(320), index=True)
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


class SimulatedOutboundInstruction(Base):
    """未来渠道执行器可消费的模拟出站指令；当前版本绝不实际发送。"""

    __tablename__ = "simulated_outbound_instructions"
    __table_args__ = (UniqueConstraint("inbound_reply_id", "action_type", name="uq_outbound_instruction_reply_action"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    template_key: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="simulated", index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class OutreachEmail(Base):
    """历史建联邮件表：用于让 Agent 知道之前发过什么。"""

    __tablename__ = "outreach_emails"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
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
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
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
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
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
        Index(
            "ix_agent_followup_runs_review_queue_reply_created",
            "inbound_reply_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index("ix_agent_followup_runs_department_created", "department_code", "created_at"),
        # PostgreSQL Worker uses this index for ordered concurrent claims.
        Index("ix_agent_followup_runs_execution_created", "execution_status", "created_at"),
        Index("ix_agent_followup_runs_execution_lease", "execution_status", "lease_expires_at"),
        Index(
            "uq_agent_followup_runs_active_reply",
            "inbound_reply_id",
            unique=True,
            postgresql_where=text("execution_status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id"), index=True)
    reply_category: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    suggested_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    llm_status: Mapped[str] = mapped_column(String(40), default="not_configured", index=True)
    block_reason: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    # execution_status 描述任务生命周期；llm_status 只描述模型或校验结果，避免混淆。
    execution_status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    claim_token: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    # Only populated while execution_status is running.  Terminal history is
    # recorded in WorkerRunEvent so the mutable run row never becomes an audit
    # log itself.
    claimed_by_worker_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    provider_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Character count is a local proxy until provider usage is integrated.
    prompt_characters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_characters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    rendered_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_materials_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkerRunEvent(Base):
    """Append-only worker claim audit event; it never stores a claim token or message content."""

    __tablename__ = "worker_run_events"
    __table_args__ = (
        Index("ix_worker_run_events_run_event_at", "agent_followup_run_id", "event_at"),
        Index("ix_worker_run_events_department_event_at", "department_code", "event_at"),
        Index("ix_worker_run_events_type_event_at", "event_type", "event_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_followup_run_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("agent_followup_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


@event.listens_for(WorkerRunEvent, "before_update")
def _prevent_worker_run_event_update(_mapper: object, _connection: object, _target: WorkerRunEvent) -> None:
    """Keep ORM callers from treating operational events as mutable state."""

    raise ValueError("worker run events are immutable")


@event.listens_for(WorkerRunEvent, "before_delete")
def _prevent_worker_run_event_delete(_mapper: object, _connection: object, _target: WorkerRunEvent) -> None:
    """The database migration adds the matching persistence-level guard."""

    raise ValueError("worker run events are immutable")


class HumanReviewDecision(Base):
    """人工对单次 Agent run 作出的最终决定；只追加，不通过业务接口修改。"""

    __tablename__ = "human_review_decisions"
    __table_args__ = (
        # 同一 run 只能被人工完成一次，避免重复确认产生相互矛盾的最终草稿。
        UniqueConstraint("agent_followup_run_id", name="uq_human_review_decisions_run"),
        # 当前没有重新审核/版本化流程，因此同一回复也只能有一个最终人工决定。
        # The unique index is the database-level concurrent-write guard.
        Index("uq_human_review_decisions_reply", "inbound_reply_id", unique=True),
        Index("ix_human_review_decisions_department_decided", "department_code", "decided_at"),
        Index(
            "ix_human_review_decisions_review_queue_outcome_department_reply",
            "outcome",
            "department_code",
            "inbound_reply_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id"), index=True)
    agent_followup_run_id: Mapped[str] = mapped_column(String(120), ForeignKey("agent_followup_runs.id"))
    outcome: Mapped[str] = mapped_column(String(40), index=True)
    final_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(120), index=True)
    decided_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class DraftExportRecord(Base):
    """人工复制或导出草稿时保存的内容快照；记录本身不代表外部消息已发送。"""

    __tablename__ = "draft_export_records"
    __table_args__ = (Index("ix_draft_export_records_department_exported", "department_code", "exported_at"),)

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), default="cross_border", index=True)
    human_review_decision_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("human_review_decisions.id"), index=True
    )
    creator_id: Mapped[str] = mapped_column(String(120), ForeignKey("creators.id"), index=True)
    inbound_reply_id: Mapped[str] = mapped_column(String(120), ForeignKey("inbound_replies.id"), index=True)
    exported_content: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(String(120), index=True)
    exported_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), index=True)


class ManualDeliveryAccount(Base):
    """Credential-free directory entry for a future owner-bound Gmail account.

    This table intentionally stores only routing, ownership and quota metadata.
    OAuth credentials and any Gmail client configuration are outside this domain.
    """

    __tablename__ = "manual_delivery_accounts"
    __table_args__ = (
        UniqueConstraint("email", name="uq_manual_delivery_accounts_email"),
        CheckConstraint("daily_limit >= 1", name="ck_manual_delivery_accounts_positive_daily_limit"),
        Index("ix_manual_delivery_accounts_department_owner_active", "department_code", "owner_auth_user_id", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    owner_auth_user_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ManualDeliveryDailyQuota(Base):
    """One account's reserved delivery capacity for one Asia/Shanghai calendar day."""

    __tablename__ = "manual_delivery_daily_quotas"
    __table_args__ = (
        UniqueConstraint("manual_delivery_account_id", "quota_date", name="uq_manual_delivery_daily_quotas_account_date"),
        CheckConstraint("reserved_count >= 0", name="ck_manual_delivery_daily_quotas_non_negative"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    manual_delivery_account_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("manual_delivery_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quota_date: Mapped[object] = mapped_column(Date, nullable=False, index=True)
    reserved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ManualDeliveryRequest(Base):
    """Auditable, owner-confirmed outbox item; it never invokes an external channel."""

    __tablename__ = "manual_delivery_requests"
    __table_args__ = (
        UniqueConstraint("human_review_decision_id", name="uq_manual_delivery_requests_decision"),
        CheckConstraint(
            "status IN ('pending_second_confirmation', 'queued', 'sending', 'sent', 'failed', 'unknown', 'expired', 'blocked_by_dnc')",
            name="ck_manual_delivery_requests_status",
        ),
        Index("ix_manual_delivery_requests_department_status_created", "department_code", "status", "created_at"),
        Index("ix_manual_delivery_requests_creator_status", "creator_id", "status"),
        Index("ix_manual_delivery_requests_expiry_status", "expires_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    department_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    human_review_decision_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("human_review_decisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    creator_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("creators.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    inbound_reply_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("inbound_replies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    manual_delivery_account_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("manual_delivery_accounts.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    draft_content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    draft_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient_email_snapshot: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gmail_thread_id_snapshot: Mapped[str | None] = mapped_column(String(320), nullable=True)
    rfc_message_id_snapshot: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    references_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_auth_user_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    second_confirmed_by_auth_user_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    account_email_snapshot: Mapped[str | None] = mapped_column(String(320), nullable=True)
    account_owner_auth_user_id_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending_second_confirmation", nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[object] = mapped_column(DateTime, nullable=False, index=True)
    quota_reserved: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
    quota_reservation_date: Mapped[object | None] = mapped_column(Date, nullable=True, index=True)
    second_confirmed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    queued_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    sending_started_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ManualDeliveryEvent(Base):
    """Append-only outbox audit event; it contains no message body or credential."""

    __tablename__ = "manual_delivery_events"
    __table_args__ = (
        Index("ix_manual_delivery_events_request_event_at", "manual_delivery_request_id", "event_at"),
        Index("ix_manual_delivery_events_department_event_at", "department_code", "event_at"),
    )

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    manual_delivery_request_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("manual_delivery_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


@event.listens_for(ManualDeliveryEvent, "before_update")
def _prevent_manual_delivery_event_update(_mapper: object, _connection: object, _target: ManualDeliveryEvent) -> None:
    raise ValueError("manual delivery events are immutable")


@event.listens_for(ManualDeliveryEvent, "before_delete")
def _prevent_manual_delivery_event_delete(_mapper: object, _connection: object, _target: ManualDeliveryEvent) -> None:
    raise ValueError("manual delivery events are immutable")


_MANUAL_DELIVERY_IMMUTABLE_SNAPSHOT_FIELDS = (
    "human_review_decision_id",
    "creator_id",
    "inbound_reply_id",
    "draft_content_snapshot",
    "draft_sha256",
    "recipient_email_snapshot",
    "subject_snapshot",
    "gmail_thread_id_snapshot",
    "rfc_message_id_snapshot",
    "references_snapshot",
    "approved_by_auth_user_id",
    "expires_at",
)


@event.listens_for(ManualDeliveryRequest, "before_update")
def _prevent_manual_delivery_snapshot_mutation(_mapper: object, _connection: object, target: ManualDeliveryRequest) -> None:
    """Keep the original reviewed draft and reply references immutable to ORM callers."""

    state = inspect(target)
    if any(state.attrs[field].history.has_changes() for field in _MANUAL_DELIVERY_IMMUTABLE_SNAPSHOT_FIELDS):
        raise ValueError("manual delivery request snapshots are immutable")
