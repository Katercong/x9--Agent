from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .department_codes import validate_department_code


REPLY_CATEGORIES = {
    "interested",
    "need_more_info",
    "negotiation",
    "not_interested",
    "bounce_or_invalid",
    "unclear",
}

SUGGESTED_STATUSES = {"pending_followup", "pending_reply", "communicating", "dropped"}
ReplyCategory = Literal[
    "interested",
    "need_more_info",
    "negotiation",
    "not_interested",
    "bounce_or_invalid",
    "unclear",
]
SuggestedStatus = Literal["pending_followup", "pending_reply", "communicating", "dropped"]
AgentNextAction = Literal[
    "send_campaign_details",
    "clarify_terms",
    "acknowledge_and_close",
    "ask_clarifying_question",
    "verify_contact_method",
    "prepare_campaign_brief",
]


class ReplyClassification(BaseModel):
    """规则层分类结果：与回复处理状态分开保存，便于解释和审计。"""

    reply_category: str
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)

    @field_validator("reply_category")
    @classmethod
    def validate_reply_category(cls, value: str) -> str:
        if value not in REPLY_CATEGORIES:
            raise ValueError(f"unknown reply_category: {value}")
        return value


class DepartmentCodeIn(BaseModel):
    """Validate request department codes against the portable ASCII namespace."""

    @field_validator("department_code", check_fields=False)
    @classmethod
    def validate_department_code_field(cls, value: str | None) -> str | None:
        return validate_department_code(value) if value is not None else None


class CreatorCreateIn(DepartmentCodeIn):
    """创建达人时使用的字段；更新需显式使用 PUT 或 PATCH。"""

    id: str
    department_code: str = "cross_border"
    platform: str = "tiktok"
    handle: str
    display_name: str | None = None
    profile_url: str | None = None
    email: str | None = None
    bio: str | None = None
    followers_count: int | None = None
    recommendation_reason: str | None = None
    recommended_product_type: str | None = None
    recommended_collab_type: str | None = None
    owner_bd: str | None = None


class CreatorReplaceIn(DepartmentCodeIn):
    """PUT 全量档案：所有档案字段必须显式提交。"""

    department_code: str
    platform: str
    handle: str
    display_name: str | None
    profile_url: str | None
    email: str | None
    bio: str | None
    followers_count: int | None
    owner_bd: str | None
    recommendation_reason: str | None
    recommended_product_type: str | None
    recommended_collab_type: str | None


class CreatorPatchIn(DepartmentCodeIn):
    """PATCH 局部档案：仅写入调用方实际传入的字段。"""

    department_code: str | None = None
    platform: str | None = None
    handle: str | None = None
    display_name: str | None = None
    profile_url: str | None = None
    email: str | None = None
    bio: str | None = None
    followers_count: int | None = None
    owner_bd: str | None = None
    recommendation_reason: str | None = None
    recommended_product_type: str | None = None
    recommended_collab_type: str | None = None


class ProductCreateIn(BaseModel):
    """创建产品档案。"""

    id: str
    product_type: str
    name: str
    summary: str
    selling_points: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    collaboration_requirements: str | None = None
    campaign_timeline: str | None = None
    campaign_deliverables: str | None = None
    budget_guidance: str | None = None
    forbidden_claims: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_active: bool = True


class ProductReplaceIn(BaseModel):
    """PUT 全量产品档案。"""

    product_type: str
    name: str
    summary: str
    selling_points: list[str]
    target_audience: str | None
    collaboration_requirements: str | None
    campaign_timeline: str | None = None
    campaign_deliverables: str | None = None
    budget_guidance: str | None = None
    forbidden_claims: list[str]
    notes: str | None
    is_active: bool


class ProductPatchIn(BaseModel):
    """PATCH 局部产品档案。"""

    product_type: str | None = None
    name: str | None = None
    summary: str | None = None
    selling_points: list[str] | None = None
    target_audience: str | None = None
    collaboration_requirements: str | None = None
    campaign_timeline: str | None = None
    campaign_deliverables: str | None = None
    budget_guidance: str | None = None
    forbidden_claims: list[str] | None = None
    notes: str | None = None
    is_active: bool | None = None


class ReferenceMaterialCreateIn(BaseModel):
    reference_key: str = Field(min_length=1, max_length=120)
    scope: Literal["company_policy", "campaign"]
    material_type: Literal["campaign_details", "pricing_terms", "company_policy"]
    product_type: str | None = None
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class ReferenceMaterialVersionIn(BaseModel):
    scope: Literal["company_policy", "campaign"]
    material_type: Literal["campaign_details", "pricing_terms", "company_policy"]
    product_type: str | None = None
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class SimulateReplyIn(BaseModel):
    creator_id: str
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body: str = Field(min_length=1, max_length=20000)
    body_format: str = Field(default="plain", pattern="^(plain|html)$")
    run_agent: bool = True


class RunAgentIn(BaseModel):
    inbound_reply_id: str


class HumanReviewDecisionCreateIn(BaseModel):
    """普通回复的人工决定；终态 DNC/拒绝不在当前接口范围内。"""

    model_config = ConfigDict(extra="forbid")

    agent_followup_run_id: str
    outcome: Literal["approve_draft", "close_without_draft"]
    final_draft: str | None = Field(default=None, max_length=20000)
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_final_draft_for_outcome(self) -> "HumanReviewDecisionCreateIn":
        # 审核结果必须有唯一语义，避免客户端提交“关闭”却附带可被误用的草稿。
        has_final_draft = bool((self.final_draft or "").strip())
        if self.outcome == "approve_draft" and not has_final_draft:
            raise ValueError("approve_draft requires a non-empty final_draft")
        if self.outcome == "close_without_draft" and self.final_draft is not None:
            raise ValueError("close_without_draft must not include final_draft")
        return self


class DncConfirmationApproveIn(BaseModel):
    """人工确认明确退订；确认后永久阻断后续业务处理，不涉及任何外发。"""

    model_config = ConfigDict(extra="forbid")


class DncConfirmationRejectIn(BaseModel):
    """人工驳回 DNC 判定；回复重新进入人工触发的 Agent 审核，不涉及任何外发。"""

    model_config = ConfigDict(extra="forbid")


class DeclineConfirmationApproveIn(BaseModel):
    """人工确认明确拒绝；操作人只从当前 Principal 派生。"""

    model_config = ConfigDict(extra="forbid")


class FailedReviewRetryIn(BaseModel):
    """人工重试模型失败的审核项；只入队新的 Agent run。"""

    model_config = ConfigDict(extra="forbid")


class DraftExportCreateIn(BaseModel):
    """记录人工复制/导出动作；不包含渠道、收件人或发送参数。"""

    model_config = ConfigDict(extra="forbid")


AccessRole = Literal["operator", "reviewer", "admin"]


class AccessUserCreateIn(BaseModel):
    """Create an Agent-local mapping for an already authenticated external identity."""

    model_config = ConfigDict(extra="forbid")

    identity_source: str = Field(min_length=1, max_length=40)
    external_subject: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)


class AccessUserPatchIn(BaseModel):
    """Only soft-state and display metadata are editable; mappings are immutable."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_an_update(self) -> "AccessUserPatchIn":
        if not self.model_fields_set:
            raise ValueError("at least one user field is required")
        return self


class AccessDepartmentCreateIn(BaseModel):
    """Create a department and assign the requesting admin as its first admin."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return validate_department_code(value)


class AccessDepartmentPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_an_update(self) -> "AccessDepartmentPatchIn":
        if not self.model_fields_set:
            raise ValueError("at least one department field is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("department name must not be null")
        return self


class AccessMembershipCreateIn(DepartmentCodeIn):
    model_config = ConfigDict(extra="forbid")

    auth_user_id: str = Field(min_length=1, max_length=120)
    department_code: str = Field(min_length=1, max_length=40)
    role: AccessRole


class AccessMembershipPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AccessRole | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_an_update(self) -> "AccessMembershipPatchIn":
        if not self.model_fields_set:
            raise ValueError("at least one membership field is required")
        return self


class AgentSuggestion(BaseModel):
    reply_category: ReplyCategory
    suggested_reply: str = Field(min_length=1)
    # 仅允许系统已实现路由的动作，避免真实模型产生无法处理的新字符串。
    next_action: AgentNextAction
    suggested_status: SuggestedStatus
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)
    # 由模型显式给出是否需要人工复核，不能只依赖置信度阈值推断。
    requires_human_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @field_validator("reply_category")
    @classmethod
    def validate_reply_category(cls, value: str) -> str:
        if value not in REPLY_CATEGORIES:
            raise ValueError(f"unknown reply_category: {value}")
        return value

    @field_validator("suggested_status")
    @classmethod
    def validate_suggested_status(cls, value: str) -> str:
        if value not in SUGGESTED_STATUSES:
            raise ValueError(f"unknown suggested_status: {value}")
        return value
