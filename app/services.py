from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .database import SessionLocal
from .llm import DEFAULT_SILICONFLOW_MODEL, SiliconFlowProviderError, call_siliconflow_json
from .models import (
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    DoNotContactConfirmation,
    FollowupTask,
    InboundReply,
    OutreachEmail,
    Product,
    ReferenceMaterial,
)
from .prompts import PromptPackage, build_prompt_package
from .schemas import AgentSuggestion, REPLY_CATEGORIES, ReplyClassification


WORKER_LEASE_SECONDS = 120


@dataclass(frozen=True)
class ClaimedRun:
    """Worker 已提交领取的任务身份，供无事务模型调用后的条件回写使用。"""

    run_id: str
    inbound_reply_id: str
    claim_token: str


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
AUTO_GENERATION_CATEGORIES = {"interested", "need_more_info", "negotiation"}
CAMPAIGN_DETAIL_REQUESTS = {
    "campaign_timeline": ("timeline", "schedule", "deadline", "时间线", "时间安排"),
    "campaign_deliverables": (
        "deliverables",
        "content requirements",
        "campaign details",
        "合作详情",
        "内容要求",
        "交付",
        "具体信息",
    ),
    "budget_guidance": ("budget", "rate", "commission", "预算", "报价", "佣金"),
}


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
    product = None
    if creator.recommended_product_type:
        product = db.scalars(
            select(Product)
            .where(Product.product_type == creator.recommended_product_type)
            .where(Product.is_active.is_(True))
            .limit(1)
        ).first()
    reference_materials = list(
        db.scalars(
            select(ReferenceMaterial)
            .where(ReferenceMaterial.is_active.is_(True))
            .where(
                (ReferenceMaterial.scope == "company_policy")
                | ((ReferenceMaterial.scope == "campaign") & (ReferenceMaterial.product_type == creator.recommended_product_type))
            )
            .order_by(ReferenceMaterial.scope.asc(), ReferenceMaterial.material_type.asc(), ReferenceMaterial.version.desc())
        ).all()
    )
    recent_inbound_replies = list(
        db.scalars(
            select(InboundReply)
            .where(InboundReply.creator_id == creator.id)
            .where(InboundReply.direction == "inbound")
            .where(InboundReply.id != reply.id)
            .order_by(InboundReply.message_at.desc().nullslast(), InboundReply.created_at.desc())
            .limit(5)
        ).all()
    )
    recent_inbound_replies.reverse()
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
        "product": _product_snapshot(product) if product else None,
        "reference_materials": [_reference_material_snapshot(row) for row in reference_materials],
        "creator": _creator_snapshot(creator),
        "inbound_reply": _reply_snapshot(reply),
        "recent_inbound_replies": [_reply_snapshot(row) for row in recent_inbound_replies],
        "recent_outreach_emails": [_email_snapshot(row) for row in recent_emails],
        "recent_events": [_event_snapshot(row) for row in recent_events],
        "open_followup_tasks": [_task_snapshot(row) for row in open_tasks],
    }


def generate_followup_suggestion(context: dict[str, Any]) -> tuple[AgentSuggestion, str]:
    category = str(context.get("reply_category") or "unclear")
    if category not in REPLY_CATEGORIES:
        category = "unclear"
    return _fallback_suggestion(category), "not_configured"


def generate_raw_followup_output(context: dict[str, Any], prompt_package: PromptPackage) -> tuple[str, str]:
    """MVP 的生成边界：后续接入 LLM 时只需替换这里的原始输出来源。"""

    if os.getenv("SILICONFLOW_API_KEY"):
        try:
            return call_siliconflow_json(prompt_package.system_prompt, prompt_package.user_prompt), "success"
        except Exception as exc:
            raise SiliconFlowProviderError("provider request failed") from exc

    suggestion, llm_status = generate_followup_suggestion(context)
    return suggestion.model_dump_json(), llm_status


def parse_followup_suggestion(raw_output: str) -> AgentSuggestion:
    """先解析 JSON，再由 Pydantic 校验建议字段和枚举值。"""

    return AgentSuggestion.model_validate(json.loads(raw_output))


def enqueue_followup_run(db: Session, inbound_reply_id: str, *, created_by: str | None = None) -> AgentFollowupRun:
    """创建可持久化的待执行任务；同一回复只能同时存在一条活跃任务。"""

    reply = db.get(InboundReply, inbound_reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    existing = db.scalars(
        select(AgentFollowupRun)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .where(AgentFollowupRun.execution_status.in_(("queued", "running")))
        .order_by(AgentFollowupRun.created_at.desc())
        .limit(1)
    ).first()
    if existing is not None:
        return existing

    # 建议尚未生成也必须进入人工待办视野，不能因后台任务延迟而停留在 new。
    if reply.processing_status != "ignored":
        reply.processing_status = "need_ai_review"

    row = AgentFollowupRun(
        id=new_id("afr"),
        department_code=reply.department_code,
        creator_id=reply.creator_id,
        inbound_reply_id=reply.id,
        reply_category=reply.reply_category or "unclear",
        llm_status="pending",
        execution_status="queued",
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    return row


def is_automatic_generation_eligible(db: Session, reply: InboundReply) -> bool:
    """规则先过滤低价值回复，只有合作推进且资料完整时才自动消耗模型额度。"""

    creator = db.get(Creator, reply.creator_id)
    if is_creator_contact_blocked(creator):
        return False
    if reply.reply_category not in AUTO_GENERATION_CATEGORIES:
        return False
    context = build_followup_context(db, reply.id)
    return bool(context.get("reference_materials")) and not collect_context_warnings(context)


def is_creator_contact_blocked(creator: Creator | None) -> bool:
    """DNC 待确认即采取保守阻断，防止误判期间继续生成或导出业务草稿。"""

    return creator is not None and creator.do_not_contact_status in {"pending_confirmation", "confirmed"}


def claim_next_queued_run(db: Session) -> ClaimedRun | None:
    """原子领取最早 queued 任务；调用方必须在模型调用前立即提交。"""

    run_id = db.scalar(
        select(AgentFollowupRun.id)
        .where(AgentFollowupRun.execution_status == "queued")
        .order_by(AgentFollowupRun.created_at.asc())
        .limit(1)
    )
    if run_id is None:
        return None
    claim_token = new_id("claim")
    claimed = db.execute(
        update(AgentFollowupRun)
        .where(AgentFollowupRun.id == run_id)
        .where(AgentFollowupRun.execution_status == "queued")
        .values(
            execution_status="running",
            started_at=datetime.utcnow(),
            claim_token=claim_token,
            lease_expires_at=datetime.utcnow() + timedelta(seconds=WORKER_LEASE_SECONDS),
        )
    )
    if claimed.rowcount != 1:
        return None
    run = db.get(AgentFollowupRun, run_id)
    if run is None or not run.inbound_reply_id:
        return None
    return ClaimedRun(run_id=run.id, inbound_reply_id=run.inbound_reply_id, claim_token=claim_token)


def recover_expired_runs(db: Session) -> int:
    """将过期 running 任务标为 worker_lost，保留给人工处理且不自动重跑。"""

    now = datetime.utcnow()
    runs = list(
        db.scalars(
            select(AgentFollowupRun)
            .where(AgentFollowupRun.execution_status == "running")
            .where(AgentFollowupRun.lease_expires_at.is_not(None))
            .where(AgentFollowupRun.lease_expires_at <= now)
        ).all()
    )
    recovered = 0
    for run in runs:
        duration_ms = int((now - run.started_at).total_seconds() * 1000) if run.started_at else 0
        updated = db.execute(
            update(AgentFollowupRun)
            .where(AgentFollowupRun.id == run.id)
            .where(AgentFollowupRun.execution_status == "running")
            .where(AgentFollowupRun.claim_token == run.claim_token)
            .where(AgentFollowupRun.lease_expires_at <= now)
            .values(
                execution_status="failed",
                llm_status="worker_lost",
                validation_error="worker lease expired before completion",
                error_summary="worker lease expired before completion",
                finished_at=now,
                duration_ms=duration_ms,
                claim_token=None,
                lease_expires_at=None,
            )
        )
        if updated.rowcount != 1:
            continue
        _update_reply_processing_status(db, run.inbound_reply_id or "", suggestion=None, requires_manual_review=True)
        recovered += 1
    db.flush()
    return recovered


def process_next_queued_run(db: Session) -> AgentFollowupRun | None:
    """兼容现有手工调用：提交领取后再由独立会话完成处理。"""

    claimed = claim_next_queued_run(db)
    if claimed is None:
        return None
    db.commit()
    return process_claimed_run(claimed)


def process_claimed_run(claimed: ClaimedRun) -> AgentFollowupRun | None:
    """在 Session 关闭后调用模型，并用领取令牌保护最终短事务回写。"""

    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, claimed.run_id)
        if not _is_current_claim(run, claimed):
            return None
        context = build_followup_context(db, claimed.inbound_reply_id)
        prompt_package = build_prompt_package(context)
        context_warnings = collect_context_warnings(context)

    if has_missing_campaign_brief(context_warnings):
        return _complete_claimed_run(
            claimed,
            context=context,
            prompt_package=prompt_package,
            suggestion=build_context_insufficient_suggestion(context, context_warnings),
            llm_status="skipped",
            execution_status="succeeded",
            block_reason="context_insufficient",
            context_warnings=context_warnings,
        )
    try:
        raw_output, llm_status = generate_raw_followup_output(context, prompt_package)
    except SiliconFlowProviderError as exc:
        return _complete_claimed_run(
            claimed,
            context=context,
            prompt_package=prompt_package,
            suggestion=None,
            llm_status="provider_error",
            execution_status="failed",
            validation_error=str(exc),
        )
    try:
        suggestion = parse_followup_suggestion(raw_output)
    except json.JSONDecodeError as exc:
        return _complete_claimed_run(
            claimed,
            context=context,
            prompt_package=prompt_package,
            suggestion=None,
            raw_output=raw_output,
            llm_status="invalid_json",
            execution_status="failed",
            validation_error=str(exc),
        )
    except ValidationError as exc:
        return _complete_claimed_run(
            claimed,
            context=context,
            prompt_package=prompt_package,
            suggestion=None,
            raw_output=raw_output,
            llm_status="validation_failed",
            execution_status="failed",
            validation_error=str(exc),
        )
    return _complete_claimed_run(
        claimed,
        context=context,
        prompt_package=prompt_package,
        suggestion=suggestion,
        llm_status=llm_status,
        execution_status="succeeded",
        context_warnings=context_warnings,
    )


def _is_current_claim(run: AgentFollowupRun | None, claimed: ClaimedRun) -> bool:
    """确认 run 仍由当前 Worker 持有，避免旧 Worker 覆盖后来状态。"""

    return bool(
        run
        and run.execution_status == "running"
        and run.claim_token == claimed.claim_token
        and run.inbound_reply_id == claimed.inbound_reply_id
    )


def _complete_claimed_run(
    claimed: ClaimedRun,
    *,
    context: dict[str, Any],
    prompt_package: PromptPackage,
    suggestion: AgentSuggestion | None,
    llm_status: str,
    execution_status: str,
    raw_output: str = "",
    validation_error: str | None = None,
    block_reason: str | None = None,
    context_warnings: list[str] | None = None,
) -> AgentFollowupRun | None:
    """以 id、claim_token 和 running 条件原子写回一次已领取任务的结果。"""

    if suggestion is not None:
        review_reasons = list(dict.fromkeys([*suggestion.review_reasons, *(context_warnings or []), "human_approval_required"]))
        suggestion = suggestion.model_copy(
            update={
                "warnings": list(dict.fromkeys([*suggestion.warnings, *review_reasons])),
                "requires_human_review": True,
                "review_reasons": review_reasons,
            }
        )
    now = datetime.utcnow()
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, claimed.run_id)
        if not _is_current_claim(run, claimed):
            return None
        output = suggestion.model_dump() if suggestion else {"raw_output": raw_output}
        duration_ms = int((now - run.started_at).total_seconds() * 1000) if run.started_at else 0
        updated = db.execute(
            update(AgentFollowupRun)
            .where(AgentFollowupRun.id == claimed.run_id)
            .where(AgentFollowupRun.execution_status == "running")
            .where(AgentFollowupRun.claim_token == claimed.claim_token)
            .values(
                reply_category=suggestion.reply_category if suggestion else str(context.get("reply_category") or "unclear"),
                suggested_status=suggestion.suggested_status if suggestion else None,
                llm_status=llm_status,
                block_reason=block_reason,
                execution_status=execution_status,
                provider_model=os.getenv("SILICONFLOW_MODEL", DEFAULT_SILICONFLOW_MODEL)
                if llm_status not in {"pending", "not_configured", "skipped"}
                else None,
                context_json=json.dumps(context, ensure_ascii=False, default=str),
                output_json=json.dumps(output, ensure_ascii=False, default=str),
                validation_error=validation_error,
                error_summary=validation_error,
                prompt_version=prompt_package.prompt_version,
                rendered_prompt=prompt_package.rendered_prompt,
                reference_materials_json=json.dumps(context.get("reference_materials") or [], ensure_ascii=False, default=str),
                prompt_characters=len(prompt_package.rendered_prompt),
                output_characters=len(json.dumps(output, ensure_ascii=False, default=str)),
                finished_at=now,
                duration_ms=duration_ms,
                claim_token=None,
                lease_expires_at=None,
            )
        )
        if updated.rowcount != 1:
            db.rollback()
            return None
        db.execute(
            update(InboundReply)
            .where(InboundReply.id == claimed.inbound_reply_id)
            .where(InboundReply.processing_status != "ignored")
            .values(processing_status="need_ai_review")
        )
        db.commit()
        return db.get(AgentFollowupRun, claimed.run_id)


def persist_unexpected_claim_error(claimed: ClaimedRun, error: Exception) -> AgentFollowupRun | None:
    """将 Worker 未预期异常立即写为失败，避免只能等待租约过期后再排障。"""

    detail = f"{type(error).__name__}: {error}"[:500]
    now = datetime.utcnow()
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, claimed.run_id)
        if not _is_current_claim(run, claimed):
            return None
        duration_ms = int((now - run.started_at).total_seconds() * 1000) if run.started_at else 0
        updated = db.execute(
            update(AgentFollowupRun)
            .where(AgentFollowupRun.id == claimed.run_id)
            .where(AgentFollowupRun.execution_status == "running")
            .where(AgentFollowupRun.claim_token == claimed.claim_token)
            .values(
                llm_status="worker_unexpected_error",
                execution_status="failed",
                validation_error=detail,
                error_summary=detail,
                finished_at=now,
                duration_ms=duration_ms,
                claim_token=None,
                lease_expires_at=None,
            )
        )
        if updated.rowcount != 1:
            db.rollback()
            return None
        db.execute(
            update(InboundReply)
            .where(InboundReply.id == claimed.inbound_reply_id)
            .where(InboundReply.processing_status != "ignored")
            .values(processing_status="need_ai_review")
        )
        db.commit()
        return db.get(AgentFollowupRun, claimed.run_id)


def process_followup_reply(
    db: Session, inbound_reply_id: str, *, run: AgentFollowupRun | None = None
) -> AgentFollowupRun:
    """集中处理建议生成、失败留痕、上下文警告和最终状态更新。"""

    context = build_followup_context(db, inbound_reply_id)
    prompt_package = build_prompt_package(context)
    context_warnings = collect_context_warnings(context)
    if has_missing_campaign_brief(context_warnings):
        return _persist_suggestion_run(
            db,
            context=context,
            suggestion=build_context_insufficient_suggestion(context, context_warnings),
            llm_status="skipped",
            prompt_package=prompt_package,
            context_warnings=context_warnings,
            run=run,
            execution_status="succeeded",
            block_reason="context_insufficient",
        )
    try:
        raw_output, llm_status = generate_raw_followup_output(context, prompt_package)
    except SiliconFlowProviderError as exc:
        return _persist_failed_run(
            db,
            context=context,
            raw_output="",
            llm_status="provider_error",
            validation_error=str(exc),
            prompt_package=prompt_package,
            run=run,
        )
    try:
        suggestion = parse_followup_suggestion(raw_output)
    except json.JSONDecodeError as exc:
        return _persist_failed_run(
            db,
            context=context,
            raw_output=raw_output,
            llm_status="invalid_json",
            validation_error=str(exc),
            prompt_package=prompt_package,
            run=run,
        )
    except ValidationError as exc:
        return _persist_failed_run(
            db,
            context=context,
            raw_output=raw_output,
            llm_status="validation_failed",
            validation_error=str(exc),
            prompt_package=prompt_package,
            run=run,
        )

    return _persist_suggestion_run(
        db,
        context=context,
        suggestion=suggestion,
        llm_status=llm_status,
        prompt_package=prompt_package,
        context_warnings=context_warnings,
        run=run,
        execution_status="succeeded",
    )


def _persist_suggestion_run(
    db: Session,
    *,
    context: dict[str, Any],
    suggestion: AgentSuggestion,
    llm_status: str,
    prompt_package: PromptPackage,
    context_warnings: list[str],
    run: AgentFollowupRun | None,
    execution_status: str,
    block_reason: str | None = None,
) -> AgentFollowupRun:
    review_reasons = list(dict.fromkeys([*suggestion.review_reasons, *context_warnings, "human_approval_required"]))
    warnings = list(dict.fromkeys([*suggestion.warnings, *review_reasons]))
    suggestion = suggestion.model_copy(
        update={
            "warnings": warnings,
            "requires_human_review": True,
            "review_reasons": review_reasons,
        }
    )
    run = persist_followup_run(
        db,
        context=context,
        suggestion=suggestion,
        llm_status=llm_status,
        prompt_package=prompt_package,
        run=run,
        execution_status=execution_status,
        block_reason=block_reason,
    )
    _update_reply_processing_status(
        db,
        str((context.get("inbound_reply") or {}).get("id") or ""),
        suggestion=suggestion,
        requires_manual_review=suggestion.requires_human_review,
    )
    return run


def has_missing_campaign_brief(warnings: list[str]) -> bool:
    return any(warning.startswith("missing_campaign_") or warning == "missing_budget_guidance" for warning in warnings)


def build_context_insufficient_suggestion(context: dict[str, Any], warnings: list[str]) -> AgentSuggestion:
    """资料不足时使用受限草稿，避免为了生成话术而调用模型并编造细节。"""

    reply = context.get("inbound_reply") or {}
    source_text = f"{reply.get('subject') or ''}\n{reply.get('body') or ''}"
    chinese_reply = bool(re.search(r"[\u4e00-\u9fff]", source_text))
    suggested_reply = (
        "感谢您的咨询。我们正在由合作负责人确认本次合作的时间线、交付内容和预算信息，确认后将由人工跟进回复您。"
        if chinese_reply
        else "Thanks for your interest. Our partnership owner is confirming the campaign timeline, deliverables, and budget guidance and will follow up with the confirmed details."
    )
    category = str(context.get("reply_category") or "need_more_info")
    return AgentSuggestion(
        reply_category=category,
        suggested_reply=suggested_reply,
        next_action="prepare_campaign_brief",
        suggested_status="pending_followup",
        confidence=1.0,
        warnings=warnings,
        reasoning_summary="Campaign details requested by the creator are missing from the approved product context.",
        requires_human_review=True,
        review_reasons=warnings,
    )


def persist_followup_run(
    db: Session,
    *,
    context: dict[str, Any],
    suggestion: AgentSuggestion | None,
    llm_status: str,
    raw_output: str | None = None,
    validation_error: str | None = None,
    prompt_package: PromptPackage | None = None,
    created_by: str | None = None,
    run: AgentFollowupRun | None = None,
    execution_status: str = "succeeded",
    block_reason: str | None = None,
) -> AgentFollowupRun:
    creator = context.get("creator") or {}
    reply = context.get("inbound_reply") or {}
    row = run or AgentFollowupRun(
        id=new_id("afr"),
        department_code=str(creator.get("department_code") or "cross_border"),
        creator_id=str(creator.get("id") or reply.get("creator_id") or ""),
        inbound_reply_id=reply.get("id"),
        created_by=created_by,
        started_at=datetime.utcnow(),
    )
    row.reply_category = suggestion.reply_category if suggestion else str(context.get("reply_category") or "unclear")
    row.suggested_status = suggestion.suggested_status if suggestion else None
    row.llm_status = llm_status
    row.block_reason = block_reason
    row.context_json = json.dumps(context, ensure_ascii=False, default=str)
    row.output_json = json.dumps(
        suggestion.model_dump() if suggestion else {"raw_output": raw_output or ""}, ensure_ascii=False, default=str
    )
    row.validation_error = validation_error
    row.prompt_version = prompt_package.prompt_version if prompt_package else None
    row.rendered_prompt = prompt_package.rendered_prompt if prompt_package else None
    row.reference_materials_json = json.dumps(context.get("reference_materials") or [], ensure_ascii=False, default=str)
    row.execution_status = execution_status
    row.prompt_characters = len(prompt_package.rendered_prompt) if prompt_package else None
    row.output_characters = len(row.output_json)
    if llm_status not in {"pending", "not_configured", "skipped"}:
        row.provider_model = os.getenv("SILICONFLOW_MODEL", DEFAULT_SILICONFLOW_MODEL)
    row.finished_at = datetime.utcnow()
    if row.started_at is None:
        row.started_at = row.finished_at
    row.duration_ms = int((row.finished_at - row.started_at).total_seconds() * 1000)
    row.error_summary = validation_error
    if run is None:
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
    prompt_package: PromptPackage,
    run: AgentFollowupRun | None,
) -> AgentFollowupRun:
    run = persist_followup_run(
        db,
        context=context,
        suggestion=None,
        llm_status=llm_status,
        raw_output=raw_output,
        validation_error=validation_error,
        prompt_package=prompt_package,
        run=run,
        execution_status="failed",
    )
    reply = context.get("inbound_reply") or {}
    _update_reply_processing_status(db, str(reply.get("id") or ""), suggestion=None, requires_manual_review=True)
    return run


def collect_context_warnings(context: dict[str, Any]) -> list[str]:
    category = str(context.get("reply_category") or "unclear")
    if category not in CONTEXT_REQUIRED_CATEGORIES:
        return []
    creator = context.get("creator") or {}
    warnings = []
    if not (creator.get("bio") or creator.get("recommendation_reason")):
        warnings.append("missing_creator_context")
    if not context.get("product"):
        warnings.append("missing_product_context")
        return warnings
    reply = context.get("inbound_reply") or {}
    normalized_reply = " ".join([str(reply.get("subject") or ""), str(reply.get("body") or "")]).lower()
    product = context.get("product") or {}
    for field, keywords in CAMPAIGN_DETAIL_REQUESTS.items():
        if _find_keyword(normalized_reply, keywords) is not None and not product.get(field):
            warnings.append(f"missing_{field}")
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
    # 除已忽略的退信外，AI 输出只能辅助人工，不能进入自动推进状态。
    reply.processing_status = "need_ai_review"
    db.flush()


def ensure_pending_followup(db: Session, creator: Creator, reply: InboundReply) -> None:
    if creator.current_status == "dropped":
        _ensure_reengagement_review(db, creator, reply)
        return
    # 收到回复只能创建人工处理入口，不能在 AI 或规则阶段自动推进达人业务状态。
    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="human_review_required",
            note="Creator replied; human review is required before business progression.",
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


def _ensure_reengagement_review(db: Session, creator: Creator, reply: InboundReply) -> None:
    """已拒绝达人重新表达意向时，仅建立人工确认入口，不自动恢复业务状态。"""

    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="reengagement_review_required",
            note="Dropped creator expressed renewed interest; human confirmation required.",
            metadata_json=json.dumps({"inbound_reply_id": reply.id}, ensure_ascii=False),
            event_at=datetime.utcnow(),
        )
    )
    existing_task = db.scalars(
        select(FollowupTask)
        .where(FollowupTask.creator_id == creator.id)
        .where(FollowupTask.task_type == "reengagement_review")
        .where(FollowupTask.status.in_(("open", "pending")))
        .limit(1)
    ).first()
    if existing_task is None:
        db.add(
            FollowupTask(
                id=new_id("task"),
                department_code=creator.department_code,
                creator_id=creator.id,
                owner_user_id=creator.owner_bd,
                task_type="reengagement_review",
                status="open",
                priority=95,
                reason="Dropped creator expressed renewed interest; confirm before restoring status.",
                due_at=datetime.utcnow(),
            )
        )
    db.flush()


def handle_creator_declined(db: Session, creator: Creator, reply: InboundReply) -> None:
    """处理明确拒绝：创建只读终态待审项，禁止在规则阶段直接写入 dropped。"""

    normalized_reply = "\n".join([reply.subject or "", reply.body]).lower()
    explicit_opt_out = _find_keyword(normalized_reply, EXPLICIT_OPT_OUT_KEYWORDS) is not None
    reply.processing_status = "need_ai_review"
    if explicit_opt_out:
        creator.do_not_contact_status = "pending_confirmation"
        creator.do_not_contact_reason = "explicit_opt_out"
        creator.do_not_contact_requested_at = datetime.utcnow()
        _ensure_dnc_confirmation(db, creator, reply)

    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="terminal_review_required",
            note="Creator declined the collaboration; human terminal review is required.",
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


def _ensure_dnc_confirmation(db: Session, creator: Creator, reply: InboundReply) -> None:
    """为明确退订创建唯一待确认流水，避免同一达人重复进入 DNC 审核队列。"""

    existing_confirmation = db.scalars(
        select(DoNotContactConfirmation)
        .where(DoNotContactConfirmation.creator_id == creator.id)
        .where(DoNotContactConfirmation.status == "pending_confirmation")
        .limit(1)
    ).first()
    if existing_confirmation is not None:
        return

    db.add(
        DoNotContactConfirmation(
            id=new_id("dnc"),
            department_code=creator.department_code,
            creator_id=creator.id,
            inbound_reply_id=reply.id,
            reason="explicit_opt_out",
            status="pending_confirmation",
        )
    )


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
    review_reasons = {
        "negotiation": ["negotiation_requires_manual_review"],
        "bounce_or_invalid": ["contact_delivery_failure"],
        "unclear": ["unclear_reply"],
    }.get(category, [])
    return AgentSuggestion(
        reply_category=category,
        suggested_reply=_suggested_reply(category),
        next_action=next_action,
        suggested_status=status,
        confidence=confidence,
        warnings=[] if not review_reasons else ["Manual review recommended."],
        reasoning_summary=reason,
        requires_human_review=bool(review_reasons),
        review_reasons=review_reasons,
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


def _product_snapshot(row: Product) -> dict[str, Any]:
    return {
        "id": row.id,
        "product_type": row.product_type,
        "name": row.name,
        "summary": row.summary,
        "selling_points": _load_json_list(row.selling_points_json),
        "target_audience": row.target_audience,
        "collaboration_requirements": row.collaboration_requirements,
        "campaign_timeline": row.campaign_timeline,
        "campaign_deliverables": row.campaign_deliverables,
        "budget_guidance": row.budget_guidance,
        "forbidden_claims": _load_json_list(row.forbidden_claims_json),
        "notes": row.notes,
    }


def _reference_material_snapshot(row: ReferenceMaterial) -> dict[str, Any]:
    """提取写入提示词和 run 审计快照所需的活动资料字段。"""

    return {"reference_key": row.reference_key, "version": row.version, "scope": row.scope, "material_type": row.material_type, "product_type": row.product_type, "title": row.title, "content": row.content}


def _load_json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


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
