from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


REPLY_CATEGORIES = {
    "interested",
    "need_more_info",
    "negotiation",
    "not_interested",
    "bounce_or_invalid",
    "unclear",
}

SUGGESTED_STATUSES = {"pending_followup", "pending_reply", "communicating", "dropped"}


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


class CreatorIn(BaseModel):
    id: str
    department_code: str = "cross_border"
    platform: str = "tiktok"
    handle: str
    display_name: str | None = None
    email: str | None = None
    bio: str | None = None
    followers_count: int | None = None
    recommendation_reason: str | None = None
    recommended_product_type: str | None = None
    recommended_collab_type: str | None = None
    owner_bd: str | None = None


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


class AgentSuggestion(BaseModel):
    reply_category: str
    suggested_reply: str = Field(min_length=1)
    next_action: str = Field(min_length=1)
    suggested_status: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)

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
