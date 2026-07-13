from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    FollowupTask,
    InboundReply,
    OutreachEmail,
)
from .schemas import AgentSuggestion, REPLY_CATEGORIES, ReplyClassification


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


KEYWORDS = {
    "bounce_or_invalid": (
        "delivery failed",
        "undeliverable",
        "mailbox unavailable",
        "invalid address",
        "退信",
        "无法送达",
        "地址无效",
    ),
    "not_interested": (
        "not interested",
        "no thanks",
        "unsubscribe",
        "remove me",
        "不感兴趣",
        "暂不考虑",
        "拒绝",
    ),
    "negotiation": (
        "rate",
        "price",
        "fee",
        "budget",
        "commission",
        "paid",
        "sample",
        "报价",
        "价格",
        "佣金",
        "预算",
        "付费",
        "寄样",
    ),
    "need_more_info": (
        "more details",
        "send details",
        "campaign details",
        "tell me more",
        "more info",
        "details",
        "资料",
        "详情",
        "更多信息",
        "介绍",
    ),
    "interested": (
        "interested",
        "happy to collaborate",
        "sounds good",
        "sounds interesting",
        "yes",
        "sure",
        "有兴趣",
        "感兴趣",
        "可以合作",
        "愿意",
    ),
}

EXPLICIT_OPT_OUT_KEYWORDS = (
    "unsubscribe",
    "remove me",
    "退订",
    "不要再联系",
    "移除我",
)

CLASSIFICATION_CONFIDENCE = {
    "interested": 0.78,
    "need_more_info": 0.82,
    "negotiation": 0.76,
    "not_interested": 0.84,
    "bounce_or_invalid": 0.88,
    "unclear": 0.52,
}

LOW_CONFIDENCE_THRESHOLD = 0.70
CONTEXT_REQUIRED_CATEGORIES = {"interested", "need_more_info", "negotiation"}


def classify_reply(text: str | None) -> str:
    return classify_reply_result(text).reply_category


def classify_reply_result(text: str | None) -> ReplyClassification:
    """返回可直接落库的规则分类、置信度和命中原因。"""

    normalized = " ".join(str(text or "").strip().lower().split())
    if not normalized:
        return ReplyClassification(reply_category="unclear", confidence=0.52, reason="no_rule_match")
    for category in ("bounce_or_invalid", "not_interested", "negotiation", "need_more_info", "interested"):
        keyword = _find_keyword(normalized, KEYWORDS[category])
        if keyword is not None:
            return ReplyClassification(
                reply_category=category,
                confidence=CLASSIFICATION_CONFIDENCE[category],
                reason=f"matched_keyword:{keyword}",
            )
    return ReplyClassification(reply_category="unclear", confidence=0.52, reason="no_rule_match")


def build_followup_context(db: Session, inbound_reply_id: str) -> dict[str, Any]:
    reply = db.get(InboundReply, inbound_reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    creator = db.get(Creator, reply.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    recent_emails = list(
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
            .order_by(FollowupTask.created_at.desc())
            .limit(10)
        ).all()
    )
    return {
        "reply_category": reply.reply_category or classify_reply("\n".join([reply.subject or "", reply.body])),
        "creator": _creator_snapshot(creator),
        "inbound_reply": _reply_snapshot(reply),
        "recent_outreach_emails": [_email_snapshot(row) for row in recent_emails],
        "recent_events": [_event_snapshot(row) for row in recent_events],
        "open_followup_tasks": [_task_snapshot(row) for row in open_tasks],
    }


def generate_followup_suggestion(context: dict[str, Any]) -> tuple[AgentSuggestion, str]:
    category = str(context.get("reply_category") or "unclear")
    if category not in REPLY_CATEGORIES:
        category = "unclear"
    return _fallback_suggestion(category), "not_configured"


def generate_raw_followup_output(context: dict[str, Any]) -> tuple[str, str]:
    """MVP 的生成边界：后续接入 LLM 时只需替换这里的原始输出来源。"""

    suggestion, llm_status = generate_followup_suggestion(context)
    return suggestion.model_dump_json(), llm_status


def parse_followup_suggestion(raw_output: str) -> AgentSuggestion:
    """先解析 JSON，再由 Pydantic 校验建议字段和枚举值。"""

    return AgentSuggestion.model_validate(json.loads(raw_output))


def process_followup_reply(db: Session, inbound_reply_id: str) -> AgentFollowupRun:
    """集中处理建议生成、失败留痕、上下文警告和最终状态更新。"""

    context = build_followup_context(db, inbound_reply_id)
    raw_output, llm_status = generate_raw_followup_output(context)
    try:
        suggestion = parse_followup_suggestion(raw_output)
    except json.JSONDecodeError as exc:
        return _persist_failed_run(
            db,
            context=context,
            raw_output=raw_output,
            llm_status="invalid_json",
            validation_error=str(exc),
        )
    except ValidationError as exc:
        return _persist_failed_run(
            db,
            context=context,
            raw_output=raw_output,
            llm_status="validation_failed",
            validation_error=str(exc),
        )

    context_warnings = _context_warnings(context)
    if context_warnings:
        warnings = list(dict.fromkeys([*suggestion.warnings, *context_warnings]))
        suggestion = suggestion.model_copy(update={"warnings": warnings})
    run = persist_followup_run(db, context=context, suggestion=suggestion, llm_status=llm_status)
    _update_reply_processing_status(
        db,
        inbound_reply_id,
        suggestion=suggestion,
        requires_manual_review=bool(context_warnings),
    )
    return run


def persist_followup_run(
    db: Session,
    *,
    context: dict[str, Any],
    suggestion: AgentSuggestion | None,
    llm_status: str,
    raw_output: str | None = None,
    validation_error: str | None = None,
    created_by: str | None = None,
) -> AgentFollowupRun:
    creator = context.get("creator") or {}
    reply = context.get("inbound_reply") or {}
    row = AgentFollowupRun(
        id=new_id("afr"),
        department_code=str(creator.get("department_code") or "cross_border"),
        creator_id=str(creator.get("id") or reply.get("creator_id") or ""),
        inbound_reply_id=reply.get("id"),
        reply_category=suggestion.reply_category if suggestion else str(context.get("reply_category") or "unclear"),
        suggested_status=suggestion.suggested_status if suggestion else None,
        llm_status=llm_status,
        context_json=json.dumps(context, ensure_ascii=False, default=str),
        output_json=json.dumps(
            suggestion.model_dump() if suggestion else {"raw_output": raw_output or ""},
            ensure_ascii=False,
            default=str,
        ),
        validation_error=validation_error,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def _persist_failed_run(
    db: Session,
    *,
    context: dict[str, Any],
    raw_output: str,
    llm_status: str,
    validation_error: str,
) -> AgentFollowupRun:
    run = persist_followup_run(
        db,
        context=context,
        suggestion=None,
        llm_status=llm_status,
        raw_output=raw_output,
        validation_error=validation_error,
    )
    reply = context.get("inbound_reply") or {}
    _update_reply_processing_status(db, str(reply.get("id") or ""), suggestion=None, requires_manual_review=True)
    return run


def _context_warnings(context: dict[str, Any]) -> list[str]:
    category = str(context.get("reply_category") or "unclear")
    if category not in CONTEXT_REQUIRED_CATEGORIES:
        return []
    creator = context.get("creator") or {}
    warnings = []
    if not (creator.get("bio") or creator.get("recommendation_reason")):
        warnings.append("missing_creator_context")
    if not creator.get("recommended_product_type"):
        warnings.append("missing_product_context")
    return warnings


def _update_reply_processing_status(
    db: Session,
    inbound_reply_id: str,
    *,
    suggestion: AgentSuggestion | None,
    requires_manual_review: bool,
) -> None:
    reply = db.get(InboundReply, inbound_reply_id)
    if reply is None or reply.processing_status == "ignored":
        return
    rule_confidence = reply.classification_confidence or 0.0
    suggestion_confidence = suggestion.confidence if suggestion else 0.0
    if (
        requires_manual_review
        or rule_confidence < LOW_CONFIDENCE_THRESHOLD
        or suggestion_confidence < LOW_CONFIDENCE_THRESHOLD
    ):
        reply.processing_status = "need_ai_review"
    else:
        reply.processing_status = "suggestion_ready"
    db.flush()


def ensure_pending_followup(db: Session, creator: Creator, reply: InboundReply) -> None:
    creator.current_status = "pending_followup"
    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="pending_followup",
            note="Creator replied; follow up now.",
            metadata_json=json.dumps({"inbound_reply_id": reply.id}, ensure_ascii=False),
            event_at=datetime.utcnow(),
        )
    )
    existing_task = db.scalars(
        select(FollowupTask)
        .where(FollowupTask.creator_id == creator.id)
        .where(FollowupTask.task_type == "reply_followup_1")
        .where(FollowupTask.status.in_(("open", "pending")))
        .limit(1)
    ).first()
    if existing_task is None:
        db.add(
            FollowupTask(
                id=new_id("fup"),
                department_code=creator.department_code,
                creator_id=creator.id,
                owner_user_id=creator.owner_bd,
                task_type="reply_followup_1",
                status="open",
                priority=90,
                reason="Creator replied; follow up now.",
                due_at=datetime.utcnow(),
            )
        )
    db.flush()


def handle_creator_declined(db: Session, creator: Creator, reply: InboundReply) -> None:
    """处理明确拒绝：终止回复跟进，并为明确退订保留人工确认入口。"""

    normalized_reply = "\n".join([reply.subject or "", reply.body]).lower()
    explicit_opt_out = _find_keyword(normalized_reply, EXPLICIT_OPT_OUT_KEYWORDS) is not None
    creator.current_status = "dropped"
    if explicit_opt_out:
        creator.do_not_contact_status = "pending_confirmation"
        creator.do_not_contact_reason = "explicit_opt_out"
        creator.do_not_contact_requested_at = datetime.utcnow()

    open_tasks = list(
        db.scalars(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator.id)
            .where(FollowupTask.task_type == "reply_followup_1")
            .where(FollowupTask.status.in_(("open", "pending")))
        ).all()
    )
    for task in open_tasks:
        task.status = "cancelled"
        task.reason = f"{task.reason or ''} Cancelled: creator declined collaboration.".strip()

    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="creator_declined",
            note="Creator declined the collaboration.",
            metadata_json=json.dumps(
                {
                    "inbound_reply_id": reply.id,
                    "do_not_contact_status": creator.do_not_contact_status,
                },
                ensure_ascii=False,
            ),
            event_at=datetime.utcnow(),
        )
    )
    db.flush()


def _fallback_suggestion(category: str) -> AgentSuggestion:
    templates = {
        "interested": ("send_campaign_details", "pending_followup", 0.78, "The creator expressed collaboration interest."),
        "need_more_info": ("send_campaign_details", "pending_followup", 0.82, "The creator asked for more campaign details."),
        "negotiation": ("clarify_terms", "pending_followup", 0.76, "The creator is discussing price, commission, samples, or terms."),
        "not_interested": ("acknowledge_and_close", "dropped", 0.84, "The creator declined the collaboration."),
        "bounce_or_invalid": ("verify_contact_method", "pending_followup", 0.88, "The reply indicates a delivery failure or invalid address."),
        "unclear": ("ask_clarifying_question", "pending_followup", 0.52, "The creator intent is unclear."),
    }
    next_action, status, confidence, reason = templates[category]
    return AgentSuggestion(
        reply_category=category,
        suggested_reply=_suggested_reply(category),
        next_action=next_action,
        suggested_status=status,
        confidence=confidence,
        warnings=[] if category not in {"negotiation", "bounce_or_invalid", "unclear"} else ["Manual review recommended."],
        reasoning_summary=reason,
    )


def _suggested_reply(category: str) -> str:
    return {
        "interested": "Thanks for your interest. I will send the collaboration details and next steps for your review.",
        "need_more_info": "Thanks for getting back to us. I will share the campaign details, product information, timeline, and deliverables here.",
        "negotiation": "Thanks for your reply. I will confirm the budget, sample arrangement, commission, and deliverable requirements before we move forward.",
        "not_interested": "Thanks for letting us know. We appreciate your time and will avoid further follow-up on this collaboration.",
        "bounce_or_invalid": "This looks like a delivery failure. Please verify the creator email or find another contact channel before continuing.",
        "unclear": "Thanks for your reply. Could you share whether you are interested in the collaboration and if you need any specific details from us?",
    }[category]


def _find_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if keyword.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text):
                return keyword
            continue
        if keyword in text:
            return keyword
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _creator_snapshot(row: Creator) -> dict[str, Any]:
    return {
        "id": row.id,
        "department_code": row.department_code,
        "platform": row.platform,
        "handle": row.handle,
        "display_name": row.display_name,
        "email": row.email,
        "bio": row.bio,
        "followers_count": row.followers_count,
        "current_status": row.current_status,
        "owner_bd": row.owner_bd,
        "recommendation_reason": row.recommendation_reason,
        "recommended_product_type": row.recommended_product_type,
        "recommended_collab_type": row.recommended_collab_type,
    }


def _reply_snapshot(row: InboundReply) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "direction": row.direction,
        "channel": row.channel,
        "external_message_id": row.external_message_id,
        "from_email": row.from_email,
        "to_email": row.to_email,
        "subject": row.subject,
        "body": row.body,
        "body_format": row.body_format,
        "message_at": _iso(row.message_at),
    }


def _email_snapshot(row: OutreachEmail) -> dict[str, Any]:
    return {"id": row.id, "subject": row.subject, "body": row.body, "status": row.status, "sent_at": _iso(row.sent_at)}


def _event_snapshot(row: CreatorOutreachEvent) -> dict[str, Any]:
    return {"id": row.id, "event_type": row.event_type, "note": row.note, "event_at": _iso(row.event_at)}


def _task_snapshot(row: FollowupTask) -> dict[str, Any]:
    return {"id": row.id, "task_type": row.task_type, "status": row.status, "reason": row.reason, "due_at": _iso(row.due_at)}
