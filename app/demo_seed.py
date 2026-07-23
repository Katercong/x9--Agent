"""为 Operator Workbench 提供可重复、无外部副作用的演示数据。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from .database import SessionLocal, init_db
from .models import (
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    DoNotContactConfirmation,
    FollowupTask,
    HumanReviewDecision,
    InboundReply,
    OutreachEmail,
    Product,
    ReferenceMaterial,
)


DEMO_DEPARTMENT = "demo_operations"
DEMO_PRODUCT_TYPE = "demo_audio_accessory"
DEMO_ACTOR_ID = "demo_operator"
DEMO_CREATED_BY = "demo_seed"
DEMO_NOW = datetime(2026, 7, 23, 9, 0, 0)

ModelT = TypeVar("ModelT")


def _add_if_missing(db: Session, model: type[ModelT], record_id: str, **values: Any) -> bool:
    """只补齐固定 demo ID，绝不覆盖操作者之后留下的本地记录。"""

    if db.get(model, record_id) is not None:
        return False
    db.add(model(id=record_id, **values))
    return True


def _creator_values(*, handle: str, display_name: str, email: str, dnc_status: str = "none") -> dict[str, Any]:
    return {
        "department_code": DEMO_DEPARTMENT,
        "platform": "demo_platform",
        "handle": handle,
        "display_name": display_name,
        "profile_url": f"https://example.invalid/{handle}",
        "bio": "虚构的演示达人资料，不对应真实个人或品牌。",
        "email": email,
        "followers_count": 126000,
        "current_status": "contacted",
        "do_not_contact_status": dnc_status,
        "owner_bd": "demo_bd",
        "recommendation_reason": "演示用合作匹配说明。",
        "recommended_product_type": DEMO_PRODUCT_TYPE,
        "recommended_collab_type": "short_video_demo",
        "created_at": DEMO_NOW,
    }


def _reply_values(
    *,
    creator_id: str,
    external_message_id: str,
    subject: str,
    body: str,
    category: str,
    confidence: float,
    reason: str,
    processing_status: str,
    message_at: datetime,
) -> dict[str, Any]:
    return {
        "department_code": DEMO_DEPARTMENT,
        "creator_id": creator_id,
        "direction": "inbound",
        "channel": "demo_seed",
        "external_message_id": external_message_id,
        "from_email": f"{creator_id}@example.invalid",
        "to_email": "bd@demo.invalid",
        "subject": subject,
        "body": body,
        "body_format": "plain",
        "message_at": message_at,
        "metadata_json": json.dumps({"source": "demo_seed"}, ensure_ascii=False),
        "processing_status": processing_status,
        "reply_category": category,
        "classification_confidence": confidence,
        "classification_reason": reason,
        "classified_at": message_at,
        "created_at": message_at,
    }


def _successful_output(reply_category: str, suggested_reply: str, next_action: str, suggested_status: str) -> str:
    return json.dumps(
        {
            "reply_category": reply_category,
            "suggested_reply": suggested_reply,
            "next_action": next_action,
            "suggested_status": suggested_status,
            "confidence": 0.9,
            "warnings": ["human_approval_required"],
            "reasoning_summary": "演示样例仅用于人工审核，不会自动改变业务状态。",
            "requires_human_review": True,
            "review_reasons": ["demo_seed_requires_human_approval", "human_approval_required"],
        },
        ensure_ascii=False,
    )


def _successful_run_values(
    *, creator_id: str, reply_id: str, category: str, output_json: str, created_at: datetime
) -> dict[str, Any]:
    return {
        "department_code": DEMO_DEPARTMENT,
        "creator_id": creator_id,
        "inbound_reply_id": reply_id,
        "reply_category": category,
        "suggested_status": "pending_reply",
        "llm_status": "success",
        "execution_status": "succeeded",
        "provider_model": "deepseek-ai/DeepSeek-V3.2",
        "started_at": created_at,
        "finished_at": created_at + timedelta(seconds=2),
        "duration_ms": 2000,
        "prompt_characters": 480,
        "output_characters": len(output_json),
        "context_json": json.dumps({"source": "demo_seed"}, ensure_ascii=False),
        "output_json": output_json,
        "prompt_version": "reply_followup_v2",
        "rendered_prompt": "[demo seed] no model request was made",
        "reference_materials_json": "[]",
        "created_by": DEMO_CREATED_BY,
        "created_at": created_at,
    }


def seed_demo_data(db: Session) -> int:
    """补齐六类工作台样例；调用方负责提交事务。"""

    created = 0

    def add(model: type[ModelT], record_id: str, **values: Any) -> None:
        nonlocal created
        created += int(_add_if_missing(db, model, record_id, **values))

    add(
        Product,
        "demo_product_audio_accessory",
        product_type=DEMO_PRODUCT_TYPE,
        name="Demo Audio Accessory",
        summary="仅用于演示审核上下文的虚构消费电子产品。",
        selling_points_json=json.dumps(["轻量便携", "长续航", "通勤场景"], ensure_ascii=False),
        target_audience="通勤与生活方式内容受众",
        collaboration_requirements="一条短视频产品体验内容。",
        campaign_timeline="演示排期：确认后两周内发布。",
        campaign_deliverables="短视频、产品体验说明和发布链接。",
        budget_guidance="演示用预算，需人工确认后再沟通。",
        forbidden_claims_json=json.dumps(["医疗功效", "绝对化承诺"], ensure_ascii=False),
        notes="所有条款均需人工审核。",
        is_active=True,
        created_at=DEMO_NOW,
    )
    add(
        ReferenceMaterial,
        "demo_reference_company_policy_v1",
        reference_key="demo-company-policy",
        version=1,
        scope="company_policy",
        material_type="company_policy",
        product_type=None,
        title="演示合作沟通边界",
        content="不得承诺自动发送、独家合作或未经确认的商务条款。",
        is_active=True,
        created_at=DEMO_NOW,
    )
    add(
        ReferenceMaterial,
        "demo_reference_campaign_details_v1",
        reference_key="demo-audio-campaign",
        version=1,
        scope="campaign",
        material_type="campaign_details",
        product_type=DEMO_PRODUCT_TYPE,
        title="演示合作资料",
        content="该资料仅供工作台展示，最终回复必须由人工确认并在外部工具中手动交接。",
        is_active=True,
        created_at=DEMO_NOW,
    )

    add(
        Creator,
        "demo_creator_standard",
        **_creator_values(handle="demo_standard", display_name="Alex Demo", email="alex.demo@example.invalid"),
    )
    add(
        Creator,
        "demo_creator_failure",
        **_creator_values(handle="demo_failure", display_name="Blair Demo", email="blair.demo@example.invalid"),
    )
    add(
        Creator,
        "demo_creator_generation",
        **_creator_values(handle="demo_generation", display_name="Casey Demo", email="casey.demo@example.invalid"),
    )
    add(
        Creator,
        "demo_creator_decline",
        **_creator_values(handle="demo_decline", display_name="Drew Demo", email="drew.demo@example.invalid"),
    )
    add(
        Creator,
        "demo_creator_dnc",
        **_creator_values(
            handle="demo_dnc", display_name="Evan Demo", email="evan.demo@example.invalid", dnc_status="pending_confirmation"
        ),
    )
    add(
        Creator,
        "demo_creator_approved",
        **_creator_values(handle="demo_approved", display_name="Fran Demo", email="fran.demo@example.invalid"),
    )
    # 模型间没有 ORM relationship 声明；显式分段 flush 以保证 SQLite 与
    # PostgreSQL 都先拥有被外键引用的达人记录。
    db.flush()

    standard_at = DEMO_NOW + timedelta(minutes=10)
    add(
        InboundReply,
        "demo_reply_standard_history",
        **_reply_values(
            creator_id="demo_creator_standard",
            external_message_id="demo:standard:history",
            subject="Earlier question",
            body="Could you share a little more information?",
            category="need_more_info",
            confidence=0.82,
            reason="demo_history",
            processing_status="reviewed",
            message_at=standard_at - timedelta(days=1),
        ),
    )
    add(
        InboundReply,
        "demo_reply_standard",
        **_reply_values(
            creator_id="demo_creator_standard",
            external_message_id="demo:standard:current",
            subject="Could you share the campaign details?",
            body="This sounds interesting. Could you share the timeline and expected deliverables?",
            category="need_more_info",
            confidence=0.82,
            reason="demo_standard_requires_human_review",
            processing_status="need_ai_review",
            message_at=standard_at,
        ),
    )
    db.flush()
    standard_output = _successful_output(
        "need_more_info",
        "Thanks for your interest. Our team will confirm the timeline and deliverables before replying with the campaign details.",
        "prepare_campaign_brief",
        "pending_reply",
    )
    add(
        AgentFollowupRun,
        "demo_run_standard",
        **_successful_run_values(
            creator_id="demo_creator_standard",
            reply_id="demo_reply_standard",
            category="need_more_info",
            output_json=standard_output,
            created_at=standard_at,
        ),
    )
    add(
        OutreachEmail,
        "demo_email_standard",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_standard",
        to_email="alex.demo@example.invalid",
        from_email="bd@demo.invalid",
        subject="Demo collaboration introduction",
        body="This is a fictional earlier outreach message used only for context.",
        status="sent",
        sent_at=standard_at - timedelta(days=2),
        created_at=standard_at - timedelta(days=2),
    )
    add(
        CreatorOutreachEvent,
        "demo_event_standard",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_standard",
        event_type="demo_context_created",
        note="演示上下文事件，不代表真实外部沟通。",
        metadata_json=json.dumps({"source": "demo_seed"}, ensure_ascii=False),
        event_at=standard_at - timedelta(days=2),
        created_at=standard_at - timedelta(days=2),
    )
    add(
        FollowupTask,
        "demo_task_standard",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_standard",
        owner_user_id="demo_bd",
        task_type="review_campaign_details",
        status="open",
        priority=30,
        reason="确认演示用合作资料后再进行人工回复。",
        due_at=standard_at + timedelta(days=1),
        created_at=standard_at,
    )

    failure_at = DEMO_NOW + timedelta(minutes=20)
    add(
        InboundReply,
        "demo_reply_failure",
        **_reply_values(
            creator_id="demo_creator_failure",
            external_message_id="demo:failure:current",
            subject="Questions about collaboration budget",
            body="What is the budget guidance for this collaboration?",
            category="negotiation",
            confidence=0.76,
            reason="demo_model_validation_failure",
            processing_status="need_ai_review",
            message_at=failure_at,
        ),
    )
    db.flush()
    add(
        AgentFollowupRun,
        "demo_run_failure",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_failure",
        inbound_reply_id="demo_reply_failure",
        reply_category="negotiation",
        llm_status="validation_failed",
        execution_status="failed",
        provider_model="deepseek-ai/DeepSeek-V3.2",
        started_at=failure_at,
        finished_at=failure_at + timedelta(seconds=1),
        duration_ms=1000,
        context_json=json.dumps({"source": "demo_seed"}, ensure_ascii=False),
        output_json=json.dumps({"raw_output": "{\"reply_draft\": \"missing schema fields\"}"}, ensure_ascii=False),
        validation_error="suggested_reply and confidence are required",
        error_summary="suggested_reply and confidence are required",
        prompt_version="reply_followup_v2",
        rendered_prompt="[demo seed] validation failure sample",
        reference_materials_json="[]",
        created_by=DEMO_CREATED_BY,
        created_at=failure_at,
    )

    generation_at = DEMO_NOW + timedelta(minutes=30)
    add(
        InboundReply,
        "demo_reply_generation",
        **_reply_values(
            creator_id="demo_creator_generation",
            external_message_id="demo:generation:current",
            subject="Interested in learning more",
            body="I am interested. Please share more details.",
            category="interested",
            confidence=0.78,
            reason="demo_generation_pending",
            processing_status="need_ai_review",
            message_at=generation_at,
        ),
    )
    db.flush()
    add(
        AgentFollowupRun,
        "demo_run_generation",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_generation",
        inbound_reply_id="demo_reply_generation",
        reply_category="interested",
        llm_status="pending",
        execution_status="queued",
        prompt_version="reply_followup_v2",
        created_by=DEMO_CREATED_BY,
        created_at=generation_at,
    )

    decline_at = DEMO_NOW + timedelta(minutes=40)
    add(
        InboundReply,
        "demo_reply_decline",
        **_reply_values(
            creator_id="demo_creator_decline",
            external_message_id="demo:decline:current",
            subject="Not interested",
            body="Thanks, but I am not interested in this collaboration.",
            category="not_interested",
            confidence=0.84,
            reason="demo_terminal_decline",
            processing_status="need_ai_review",
            message_at=decline_at,
        ),
    )

    dnc_at = DEMO_NOW + timedelta(minutes=50)
    add(
        InboundReply,
        "demo_reply_dnc",
        **_reply_values(
            creator_id="demo_creator_dnc",
            external_message_id="demo:dnc:current",
            subject="Please stop contacting me",
            body="Please unsubscribe me from future messages.",
            category="not_interested",
            confidence=0.99,
            reason="demo_explicit_opt_out",
            processing_status="need_ai_review",
            message_at=dnc_at,
        ),
    )
    db.flush()
    add(
        DoNotContactConfirmation,
        "demo_dnc_confirmation",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_dnc",
        inbound_reply_id="demo_reply_dnc",
        reason="explicit_opt_out",
        status="pending_confirmation",
        created_at=dnc_at,
    )

    approved_at = DEMO_NOW + timedelta(minutes=60)
    add(
        InboundReply,
        "demo_reply_approved",
        **_reply_values(
            creator_id="demo_creator_approved",
            external_message_id="demo:approved:current",
            subject="Ready to review next steps",
            body="The proposed approach works for me. What are the next steps?",
            category="interested",
            confidence=0.78,
            reason="demo_approved_draft",
            processing_status="reviewed",
            message_at=approved_at,
        ),
    )
    db.flush()
    approved_output = _successful_output(
        "interested",
        "Thanks for confirming. We will prepare the next steps and share them after a final human review.",
        "prepare_campaign_brief",
        "pending_reply",
    )
    add(
        AgentFollowupRun,
        "demo_run_approved",
        **_successful_run_values(
            creator_id="demo_creator_approved",
            reply_id="demo_reply_approved",
            category="interested",
            output_json=approved_output,
            created_at=approved_at,
        ),
    )
    db.flush()
    add(
        HumanReviewDecision,
        "demo_decision_approved",
        department_code=DEMO_DEPARTMENT,
        creator_id="demo_creator_approved",
        inbound_reply_id="demo_reply_approved",
        agent_followup_run_id="demo_run_approved",
        outcome="approve_draft",
        final_draft="Thanks for confirming. We will share the next steps after the BD team completes the final manual check.",
        note="演示：已批准并锁定，仍需由 BD 手动复制或下载交接。",
        actor_id=DEMO_ACTOR_ID,
        decided_at=approved_at + timedelta(seconds=5),
        created_at=approved_at + timedelta(seconds=5),
    )

    db.flush()
    return created


def main() -> None:
    """CLI 入口：在已由 migrate 服务升级的数据库中补齐样例数据。"""

    init_db()
    with SessionLocal() as db:
        try:
            created = seed_demo_data(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(f"demo seed complete: {created} record(s) created")


if __name__ == "__main__":
    main()
