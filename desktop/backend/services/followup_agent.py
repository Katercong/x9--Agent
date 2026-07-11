from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.agent_followup_run import AgentFollowupRun
from ..models.creator import Creator
from ..models.creator_email_message import CreatorEmailMessage
from ..models.creator_outreach_event import CreatorOutreachEvent
from ..models.followup_task import FollowupTask
from ..models.outreach_email import OutreachEmail
from ..utils.id_utils import new_id


REPLY_CATEGORIES = {
    "interested",
    "need_more_info",
    "negotiation",
    "not_interested",
    "bounce_or_invalid",
    "unclear",
}

SUGGESTED_STATUSES = {
    "pending_followup",
    "pending_reply",
    "communicating",
    "dropped",
}


BOUNCE_KEYWORDS = (
    "delivery failed",
    "undeliverable",
    "mailbox unavailable",
    "address invalid",
    "invalid address",
    "bounce",
    "退信",
    "无法送达",
    "地址无效",
)

NOT_INTERESTED_KEYWORDS = (
    "not interested",
    "no thanks",
    "unsubscribe",
    "remove me",
    "不感兴趣",
    "暂不考虑",
    "不用了",
    "拒绝",
)

NEGOTIATION_KEYWORDS = (
    "rate",
    "price",
    "fee",
    "budget",
    "commission",
    "paid",
    "payment",
    "sample",
    "报价",
    "价格",
    "佣金",
    "预算",
    "付费",
    "寄样",
)

NEED_MORE_INFO_KEYWORDS = (
    "more details",
    "send details",
    "campaign details",
    "tell me more",
    "more info",
    "information",
    "details",
    "资料",
    "详情",
    "更多信息",
    "介绍",
)

INTERESTED_KEYWORDS = (
    "interested",
    "happy to collaborate",
    "sounds good",
    "sounds interesting",
    "let's do",
    "yes",
    "sure",
    "有兴趣",
    "感兴趣",
    "可以合作",
    "愿意",
)


class AgentSuggestion(BaseModel):
    """LLM 或 fallback 必须产出的结构化建议。"""

    reply_category: str
    suggested_reply: str = Field(min_length=1)
    next_action: str = Field(min_length=1)
    suggested_status: str
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str = Field(min_length=1)

    @field_validator("reply_category")
    @classmethod
    def _validate_reply_category(cls, value: str) -> str:
        if value not in REPLY_CATEGORIES:
            raise ValueError(f"unknown reply_category: {value}")
        return value

    @field_validator("suggested_status")
    @classmethod
    def _validate_suggested_status(cls, value: str) -> str:
        if value not in SUGGESTED_STATUSES:
            raise ValueError(f"unknown suggested_status: {value}")
        return value


def classify_reply(text: str | None) -> str:
    """用确定性规则给达人回复做第一层分类，作为后续 LLM 的稳定先验。"""

    normalized = _normalize_text(text)
    if not normalized:
        return "unclear"

    # 顺序很重要：拒绝和退信优先，避免 "not interested" 被 interested 误伤。
    if _contains_any(normalized, BOUNCE_KEYWORDS):
        return "bounce_or_invalid"
    if _contains_any(normalized, NOT_INTERESTED_KEYWORDS):
        return "not_interested"
    if _contains_any(normalized, NEGOTIATION_KEYWORDS):
        return "negotiation"
    if _contains_any(normalized, NEED_MORE_INFO_KEYWORDS):
        return "need_more_info"
    if _contains_any(normalized, INTERESTED_KEYWORDS):
        return "interested"
    return "unclear"


def build_followup_context(db: Session, inbound_message_id: str) -> dict[str, Any]:
    """围绕一条入站回复构建 agent 可复盘的上下文快照。"""

    message = db.get(CreatorEmailMessage, inbound_message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="inbound message not found")
    if message.direction not in {"inbound", "bounce"}:
        raise HTTPException(status_code=400, detail="message is not an inbound reply")

    creator = db.get(Creator, message.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")

    reply_text = _message_text(message)
    recent_outreach = list(
        db.scalars(
            select(OutreachEmail)
            .where(OutreachEmail.creator_id == creator.id)
            .order_by(OutreachEmail.sent_at.desc().nullslast(), OutreachEmail.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_events = list(
        db.scalars(
            select(CreatorOutreachEvent)
            .where(CreatorOutreachEvent.creator_id == creator.id)
            .order_by(CreatorOutreachEvent.event_at.desc(), CreatorOutreachEvent.created_at.desc())
            .limit(10)
        ).all()
    )
    open_tasks = list(
        db.scalars(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator.id)
            .where(FollowupTask.status.in_(("open", "pending")))
            .order_by(FollowupTask.due_at.asc().nullslast(), FollowupTask.created_at.desc())
            .limit(10)
        ).all()
    )

    return {
        "reply_category": classify_reply(reply_text),
        "creator": _creator_snapshot(creator),
        "inbound_message": _message_snapshot(message),
        "recent_outreach_emails": [_outreach_snapshot(row) for row in recent_outreach],
        "recent_events": [_event_snapshot(row) for row in recent_events],
        "open_followup_tasks": [_task_snapshot(row) for row in open_tasks],
    }


def generate_followup_suggestion(context: dict[str, Any]) -> tuple[AgentSuggestion, str]:
    """生成后续人工跟进建议；MVP 先保证无 key 时有稳定 fallback。"""

    category = str(context.get("reply_category") or "unclear")
    if category not in REPLY_CATEGORIES:
        category = "unclear"

    # 后续接入 LLM 时仍复用 AgentSuggestion 做最终边界校验。
    if not settings.openai_api_key:
        return _fallback_suggestion(category), "not_configured"
    return _fallback_suggestion(category), "fallback"


def persist_followup_run(
    db: Session,
    *,
    context: dict[str, Any],
    suggestion: AgentSuggestion | dict[str, Any] | None,
    llm_status: str,
    created_by: str | None = None,
    run_id: str | None = None,
    validation_error: str | None = None,
) -> AgentFollowupRun:
    """把 agent 运行输入和输出写入留痕表，方便后续复盘。"""

    inbound_message = context.get("inbound_message") or {}
    creator = context.get("creator") or {}
    output_payload: dict[str, Any] | None = None
    suggested_status: str | None = None
    reply_category = str(context.get("reply_category") or "") or None

    if isinstance(suggestion, AgentSuggestion):
        output_payload = _model_to_dict(suggestion)
        reply_category = suggestion.reply_category
        suggested_status = suggestion.suggested_status
    elif isinstance(suggestion, dict):
        validated = AgentSuggestion(**suggestion)
        output_payload = _model_to_dict(validated)
        reply_category = validated.reply_category
        suggested_status = validated.suggested_status

    row = AgentFollowupRun(
        id=run_id or new_id("afr"),
        department_code=str(creator.get("department_code") or inbound_message.get("department_code") or "cross_border"),
        creator_id=str(creator.get("id") or inbound_message.get("creator_id") or ""),
        inbound_message_id=inbound_message.get("id"),
        reply_category=reply_category,
        suggested_status=suggested_status,
        llm_status=llm_status,
        context_json=json.dumps(context, ensure_ascii=False, default=str),
        output_json=json.dumps(output_payload, ensure_ascii=False, default=str) if output_payload is not None else None,
        validation_error=validation_error,
        created_by=created_by,
    )
    db.add(row)
    return row


def _fallback_suggestion(category: str) -> AgentSuggestion:
    templates: dict[str, dict[str, Any]] = {
        "interested": {
            "suggested_reply": "Thanks for your interest. I will send the collaboration details, product info, and next steps for your review.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.78,
            "warnings": [],
            "reasoning_summary": "The creator expressed positive collaboration intent.",
        },
        "need_more_info": {
            "suggested_reply": "Thanks for getting back to us. I will share the campaign details, product information, timeline, and expected deliverables here.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.82,
            "warnings": [],
            "reasoning_summary": "The creator asked for more information before deciding.",
        },
        "negotiation": {
            "suggested_reply": "Thanks for your reply. I will confirm the budget, sample arrangement, commission, and deliverable requirements before we move forward.",
            "next_action": "clarify_terms",
            "suggested_status": "pending_followup",
            "confidence": 0.76,
            "warnings": ["Check pricing and commission terms before promising anything."],
            "reasoning_summary": "The creator is discussing commercial terms or sample conditions.",
        },
        "not_interested": {
            "suggested_reply": "Thanks for letting us know. We appreciate your time and will avoid further follow-up on this collaboration.",
            "next_action": "acknowledge_and_close",
            "suggested_status": "dropped",
            "confidence": 0.84,
            "warnings": ["Do not continue outreach unless the creator reopens the conversation."],
            "reasoning_summary": "The creator clearly declined the collaboration.",
        },
        "bounce_or_invalid": {
            "suggested_reply": "This looks like a delivery failure. Please verify the creator email or find another contact channel before continuing.",
            "next_action": "verify_contact_method",
            "suggested_status": "pending_followup",
            "confidence": 0.88,
            "warnings": ["Do not send another email until the address is verified."],
            "reasoning_summary": "The message indicates an invalid mailbox or failed delivery.",
        },
        "unclear": {
            "suggested_reply": "Thanks for your reply. Could you share whether you are interested in the collaboration and if you need any specific details from us?",
            "next_action": "ask_clarifying_question",
            "suggested_status": "pending_followup",
            "confidence": 0.52,
            "warnings": ["Intent is unclear; keep the reply short and ask one direct question."],
            "reasoning_summary": "The reply does not provide enough signal to classify intent confidently.",
        },
    }
    return AgentSuggestion(reply_category=category, **templates[category])


def _model_to_dict(model: AgentSuggestion) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _normalize_text(text: str | None) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    for keyword in keywords:
        if keyword.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return True
            continue
        if keyword in text:
            return True
    return False


def _message_text(message: CreatorEmailMessage) -> str:
    parts = [message.subject, message.snippet, message.body_preview, message.body]
    return "\n".join(str(part) for part in parts if part)


def _iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None if value is None else str(value)


def _creator_snapshot(creator: Creator) -> dict[str, Any]:
    return {
        "id": creator.id,
        "department_code": creator.department_code,
        "platform": creator.platform,
        "handle": creator.handle,
        "display_name": creator.display_name,
        "profile_url": creator.profile_url,
        "bio": creator.bio,
        "email": creator.email,
        "followers_count": creator.followers_count,
        "current_status": creator.current_status,
        "owner_bd": creator.owner_bd,
        "recommendation_reason": creator.recommendation_reason,
        "recommended_product_type": creator.recommended_product_type,
        "recommended_collab_type": creator.recommended_collab_type,
    }


def _message_snapshot(message: CreatorEmailMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "department_code": message.department_code,
        "creator_id": message.creator_id,
        "outreach_email_id": message.outreach_email_id,
        "gmail_thread_id": message.gmail_thread_id,
        "gmail_message_id": message.gmail_message_id,
        "direction": message.direction,
        "from_email": message.from_email,
        "to_email": message.to_email,
        "subject": message.subject,
        "snippet": message.snippet,
        "body_preview": message.body_preview,
        "body": message.body,
        "body_format": message.body_format,
        "message_at": _iso(message.message_at),
    }


def _outreach_snapshot(email: OutreachEmail) -> dict[str, Any]:
    return {
        "id": email.id,
        "creator_id": email.creator_id,
        "to_email": email.to_email,
        "from_email": email.from_email,
        "subject": email.subject,
        "body": email.body,
        "body_format": email.body_format,
        "status": email.status,
        "gmail_thread_id": email.gmail_thread_id,
        "sent_at": _iso(email.sent_at),
        "created_at": _iso(email.created_at),
    }


def _event_snapshot(event: CreatorOutreachEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "creator_id": event.creator_id,
        "event_type": event.event_type,
        "actor_user_id": event.actor_user_id,
        "owner_bd": event.owner_bd,
        "note": event.note,
        "metadata_json": event.metadata_json,
        "event_at": _iso(event.event_at),
    }


def _task_snapshot(task: FollowupTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "creator_id": task.creator_id,
        "owner_user_id": task.owner_user_id,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "reason": task.reason,
        "due_at": _iso(task.due_at),
        "completed_at": _iso(task.completed_at),
    }
