from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from desktop.backend.database.connection import SessionLocal, init_db
from desktop.backend.models.creator import Creator
from desktop.backend.models.creator_email_message import CreatorEmailMessage
from desktop.backend.models.creator_outreach_event import CreatorOutreachEvent
from desktop.backend.models.agent_followup_run import AgentFollowupRun
from desktop.backend.models.followup_task import FollowupTask
from desktop.backend.models.outreach_email import OutreachEmail


@pytest.fixture(scope="module", autouse=True)
def _init_desktop_db():
    init_db()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sounds interesting, happy to collaborate with X9.", "interested"),
        ("Can you send more details about the campaign?", "need_more_info"),
        ("What is your rate and commission for this collab?", "negotiation"),
        ("Thanks, but I am not interested right now.", "not_interested"),
        ("Delivery failed: mailbox unavailable, address invalid.", "bounce_or_invalid"),
        ("Thanks.", "unclear"),
    ],
)
def test_classify_reply_maps_common_creator_replies(text, expected):
    """模块 3：先用规则分类达人回复，LLM 前也要有稳定先验。"""
    from desktop.backend.services.followup_agent import classify_reply

    assert classify_reply(text) == expected


def test_build_followup_context_collects_creator_message_history_events_and_tasks():
    """模块 3：上下文需要串起达人、入站回复、历史邮件、事件和人工待办。"""
    from desktop.backend.services.followup_agent import build_followup_context

    creator_id = "creator_followup_context_m3"
    inbound_id = "cem_followup_context_m3"
    sent_id = "oe_followup_context_m3"
    event_id = "coe_followup_context_m3"
    task_id = "ft_followup_context_m3"
    now = datetime(2026, 7, 11, 10, 0, 0)

    with SessionLocal() as session:
        _cleanup_context_rows(session, creator_id, inbound_id, sent_id, event_id, task_id)
        session.add(
            Creator(
                id=creator_id,
                platform="tiktok",
                department_code="cross_border",
                handle="reply_agent_test",
                display_name="Reply Agent Test",
                profile_url="https://www.tiktok.com/@reply_agent_test",
                bio="Reviews mom and baby daily care products.",
                email="creator@example.com",
                has_email=1,
                followers_count=28000,
                recommendation_reason="Audience overlaps with mom and baby care.",
                recommended_product_type="mom_baby",
                recommended_collab_type="sample_collab",
                current_status="pending_followup",
                owner_bd="Alice",
            )
        )
        session.add(
            OutreachEmail(
                id=sent_id,
                department_code="cross_border",
                creator_id=creator_id,
                to_email="creator@example.com",
                from_email="bd@x9.com",
                subject="Collaboration details",
                body="We would like to send a sample for review.",
                body_format="plain",
                status="sent",
                sent_at=now - timedelta(days=1),
            )
        )
        session.add(
            CreatorEmailMessage(
                id=inbound_id,
                department_code="cross_border",
                creator_id=creator_id,
                outreach_email_id=sent_id,
                gmail_account_id="gmail_context_m3",
                gmail_message_id="gmail_msg_context_m3",
                gmail_thread_id="gmail_thread_context_m3",
                direction="inbound",
                from_email="creator@example.com",
                to_email="bd@x9.com",
                subject="Re: Collaboration details",
                snippet="Can you send more campaign details?",
                body_preview="Can you send more campaign details?",
                body="Can you send more campaign details and timing?",
                body_format="plain",
                message_at=now,
            )
        )
        session.add(
            CreatorOutreachEvent(
                id=event_id,
                department_code="cross_border",
                creator_id=creator_id,
                event_type="pending_followup",
                actor_user_id="gmail_sync",
                note="Creator replied from Gmail.",
                event_at=now,
            )
        )
        session.add(
            FollowupTask(
                id=task_id,
                department_code="cross_border",
                creator_id=creator_id,
                owner_user_id="alice",
                task_type="reply_followup_1",
                status="open",
                priority=30,
                reason="Creator asked for more details.",
                due_at=now + timedelta(days=1),
            )
        )
        session.commit()

        context = build_followup_context(session, inbound_id)

        assert context["reply_category"] == "need_more_info"
        assert context["creator"]["id"] == creator_id
        assert context["creator"]["handle"] == "reply_agent_test"
        assert context["creator"]["recommendation_reason"] == "Audience overlaps with mom and baby care."
        assert context["inbound_message"]["id"] == inbound_id
        assert "campaign details" in context["inbound_message"]["body"]
        assert context["recent_outreach_emails"][0]["id"] == sent_id
        assert context["recent_events"][0]["event_type"] == "pending_followup"
        assert context["open_followup_tasks"][0]["id"] == task_id
        assert context["open_followup_tasks"][0]["status"] == "open"

        _cleanup_context_rows(session, creator_id, inbound_id, sent_id, event_id, task_id)
        session.commit()


def test_generate_followup_suggestion_uses_validated_fallback_when_llm_not_configured(monkeypatch):
    """模块 4：没有 OpenAI key 时也要产出可校验的确定性建议。"""
    from desktop.backend.services import followup_agent

    monkeypatch.setattr(followup_agent, "settings", SimpleNamespace(openai_api_key=""))
    context = {
        "reply_category": "need_more_info",
        "creator": {"display_name": "Reply Agent Test"},
        "inbound_message": {"body": "Can you send more campaign details?"},
        "recent_outreach_emails": [],
        "recent_events": [],
        "open_followup_tasks": [],
    }

    suggestion, llm_status = followup_agent.generate_followup_suggestion(context)

    assert llm_status == "not_configured"
    assert suggestion.reply_category == "need_more_info"
    assert suggestion.suggested_status == "pending_followup"
    assert suggestion.next_action == "send_campaign_details"
    assert 0 <= suggestion.confidence <= 1
    assert suggestion.suggested_reply


def test_agent_suggestion_rejects_invalid_category_and_confidence():
    """模块 4：Pydantic schema 要挡住不受控的模型输出。"""
    from pydantic import ValidationError

    from desktop.backend.services.followup_agent import AgentSuggestion

    with pytest.raises(ValidationError):
        AgentSuggestion(
            reply_category="random",
            suggested_reply="Thanks.",
            next_action="reply",
            suggested_status="pending_followup",
            confidence=1.5,
            warnings=[],
            reasoning_summary="Invalid category should fail.",
        )


def test_persist_followup_run_saves_context_output_and_validation_state(monkeypatch):
    """模块 4：每次 agent 建议都要写入 agent_followup_runs 留痕表。"""
    from desktop.backend.services import followup_agent

    run_id = "afr_module4_persist"
    inbound_id = "cem_module4_persist"
    creator_id = "creator_module4_persist"
    monkeypatch.setattr(followup_agent, "settings", SimpleNamespace(openai_api_key=""))

    with SessionLocal() as session:
        session.query(AgentFollowupRun).filter_by(id=run_id).delete()
        context = {
            "reply_category": "interested",
            "creator": {"id": creator_id, "display_name": "Module 4 Creator"},
            "inbound_message": {"id": inbound_id, "body": "Yes, sounds interesting."},
            "recent_outreach_emails": [],
            "recent_events": [],
            "open_followup_tasks": [],
        }
        suggestion, llm_status = followup_agent.generate_followup_suggestion(context)

        saved = followup_agent.persist_followup_run(
            session,
            context=context,
            suggestion=suggestion,
            llm_status=llm_status,
            created_by="module4_test",
            run_id=run_id,
        )
        session.commit()

        row = session.get(AgentFollowupRun, saved.id)
        assert row is not None
        assert row.id == run_id
        assert row.creator_id == creator_id
        assert row.inbound_message_id == inbound_id
        assert row.reply_category == "interested"
        assert row.suggested_status == "pending_followup"
        assert row.llm_status == "not_configured"
        assert row.validation_error is None
        assert "Module 4 Creator" in (row.context_json or "")
        assert "suggested_reply" in (row.output_json or "")

        session.delete(row)
        session.commit()


def _cleanup_context_rows(
    session,
    creator_id: str,
    inbound_id: str,
    sent_id: str,
    event_id: str,
    task_id: str,
) -> None:
    session.query(FollowupTask).filter_by(id=task_id).delete()
    session.query(CreatorOutreachEvent).filter_by(id=event_id).delete()
    session.query(CreatorEmailMessage).filter_by(id=inbound_id).delete()
    session.query(OutreachEmail).filter_by(id=sent_id).delete()
    row = session.get(Creator, creator_id)
    if row is not None:
        session.delete(row)
