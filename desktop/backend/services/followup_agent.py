from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.creator_email_message import CreatorEmailMessage
from ..models.creator_outreach_event import CreatorOutreachEvent
from ..models.followup_task import FollowupTask
from ..models.outreach_email import OutreachEmail


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
