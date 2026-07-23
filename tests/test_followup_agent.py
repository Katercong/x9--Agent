from __future__ import annotations

import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False, suffix='.db').name}"
# 单元测试必须使用本地 fallback，避免读取开发者 .env 后意外消耗真实模型额度。
os.environ["SILICONFLOW_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.demo_seed import seed_demo_data  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    DraftExportRecord,
    FollowupTask,
    HumanReviewDecision,
    InboundReply,
)
from app import models, services  # noqa: E402
from app.schemas import AgentSuggestion  # noqa: E402
from app.services import classify_reply  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    """每个用例使用干净表结构，避免上一条回复影响本用例的状态和计数。"""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    if hasattr(models, "Product"):
        with SessionLocal() as db:
            db.add(
                models.Product(
                    id="product_default_baby_care",
                    product_type="baby care",
                    name="Baby Care Starter",
                    summary="Daily baby care product for young families.",
                    selling_points_json=json.dumps(["gentle formula", "easy daily use"]),
                    target_audience="Parents of young children",
                    collaboration_requirements="One short product demonstration video.",
                    forbidden_claims_json=json.dumps(["medical cure claims"]),
                    notes="Avoid health treatment promises.",
                    is_active=True,
                )
            )
            db.add(
                models.ReferenceMaterial(
                    id="ref_default_company_policy_v1",
                    reference_key="default-company-policy",
                    version=1,
                    scope="company_policy",
                    material_type="company_policy",
                    title="Default company policy",
                    content="Do not promise exclusivity, guaranteed results, or unapproved terms.",
                    is_active=True,
                )
            )
            db.commit()


def test_classify_reply_categories():
    assert classify_reply("Sounds interesting, happy to collaborate.") == "interested"
    assert classify_reply("Can you send more campaign details?") == "need_more_info"
    assert classify_reply("What is your rate and commission?") == "negotiation"
    assert classify_reply("Thanks but not interested.") == "not_interested"
    assert classify_reply("Delivery failed, invalid address.") == "bounce_or_invalid"
    assert classify_reply("Thanks.") == "unclear"

    assert classify_reply("我有兴趣，可以合作。") == "interested"
    assert classify_reply("请发更多详情。") == "need_more_info"
    assert classify_reply("请问报价和佣金是多少？") == "negotiation"
    assert classify_reply("谢谢，但我们暂不考虑。") == "not_interested"
    assert classify_reply("邮件无法送达，地址无效。") == "bounce_or_invalid"
    assert classify_reply("谢谢。") == "unclear"


def test_classify_reply_result_includes_confidence_and_reason():
    assert hasattr(services, "classify_reply_result")
    matched = services.classify_reply_result("Sounds interesting, happy to collaborate.")
    assert matched.reply_category == "interested"
    assert matched.confidence == 0.78
    assert matched.reason.startswith("matched_keyword:")

    unclear = services.classify_reply_result("Thanks.")
    assert unclear.reply_category == "unclear"
    assert unclear.confidence == 0.52
    assert unclear.reason == "no_rule_match"


def test_simulate_reply_runs_agent_and_persists_run():
    init_db()
    client = TestClient(app)
    creator = client.post(
        "/api/followup-agent/creators",
        json={
            "id": "creator_test_1",
            "handle": "creator_test",
            "display_name": "Creator Test",
            "email": "creator@example.com",
            "recommendation_reason": "Audience overlaps with mom and baby care.",
            "recommended_product_type": "baby care",
        },
    )
    assert creator.status_code == 201, creator.text

    reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": "creator_test_1",
            "from_email": "creator@example.com",
            "subject": "Re: Collaboration",
            "body": "Sounds interesting. Can you send more campaign details?",
            "run_agent": True,
        },
    )
    assert reply.status_code == 200, reply.text
    payload = reply.json()
    assert payload["run"] is None
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert payload["reply"]["reply_category"] == "need_more_info"
    assert payload["reply"]["classification_confidence"] == 0.82
    assert payload["reply"]["classification_reason"].startswith("matched_keyword:")
    assert payload["reply"]["classified_at"] is not None

    manual = client.post("/api/followup-agent/runs", json={"inbound_reply_id": payload["reply"]["id"]})
    assert manual.status_code == 200, manual.text
    completed_run = _process_response_run(client, manual)
    assert completed_run["llm_status"] == "skipped"
    assert completed_run["execution_status"] == "succeeded"
    assert completed_run["block_reason"] == "context_insufficient"
    assert completed_run["output"]["next_action"] == "prepare_campaign_brief"
    assert completed_run["output"]["requires_human_review"] is True
    assert "human_approval_required" in completed_run["output"]["warnings"]

    listed = client.get("/api/followup-agent/runs?creator_id=creator_test_1")
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1


def test_run_agent_false_keeps_new_status_and_reply_can_be_queried():
    init_db()
    client = TestClient(app)
    creator_id = "creator_status_new"
    _create_creator(client, creator_id)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": creator_id,
            "subject": "Re: Details",
            "body": "Can you send more campaign details?",
            "run_agent": False,
        },
    )
    assert response.status_code == 200, response.text
    reply = response.json()["reply"]
    assert reply["processing_status"] == "new"
    assert reply["reply_category"] == "need_more_info"
    assert reply["classification_confidence"] == 0.82

    fetched = client.get(f"/api/followup-agent/replies/{reply['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["reply"] == reply


def test_unclear_reply_moves_to_need_ai_review_after_run():
    init_db()
    client = TestClient(app)
    creator_id = "creator_status_review"
    _create_creator(client, creator_id)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Thanks.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"]["processing_status"] == "need_ai_review"


def test_bounce_reply_is_ignored_without_followup_side_effects():
    init_db()
    client = TestClient(app)
    creator_id = "creator_status_ignored"
    _create_creator(client, creator_id)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Delivery failed, invalid address.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "ignored"
    assert payload["reply"]["reply_category"] == "bounce_or_invalid"
    assert payload["run"] is None

    with SessionLocal() as db:
        assert hasattr(models, "DoNotContactConfirmation")
        confirmation_model = models.DoNotContactConfirmation
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status is None
        assert db.scalar(
            select(func.count()).select_from(CreatorOutreachEvent).where(CreatorOutreachEvent.creator_id == creator_id)
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(FollowupTask).where(FollowupTask.creator_id == creator_id)
        ) == 0
        assert db.scalar(
            select(func.count()).select_from(AgentFollowupRun).where(AgentFollowupRun.creator_id == creator_id)
        ) == 0


def test_not_interested_enters_terminal_review_without_dropping_creator_or_cancelling_task():
    client = TestClient(app)
    creator_id = "creator_declined"
    _create_creator(client, creator_id)

    first_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": False},
    )
    assert first_reply.status_code == 200, first_reply.text

    rejection = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Thanks, but not interested.", "run_agent": True},
    )
    assert rejection.status_code == 200, rejection.text
    assert rejection.json()["run"] is None
    assert rejection.json()["reply"]["processing_status"] == "need_ai_review"

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status is None
        assert creator.do_not_contact_status == "none"
        tasks = list(db.scalars(select(FollowupTask).where(FollowupTask.creator_id == creator_id)).all())
        assert len(tasks) == 1
        assert tasks[0].status == "open"
        event_types = list(
            db.scalars(
                select(CreatorOutreachEvent.event_type).where(CreatorOutreachEvent.creator_id == creator_id)
            ).all()
        )
        assert event_types.count("terminal_review_required") == 1

    queue = client.get("/api/followup-agent/review-queue?review_type=decline")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["decision_available"] is False


def test_unconfirmed_decline_does_not_create_reengagement_task_for_later_reply():
    """拒绝未被终态确认前，后续意向回复仍不能触发 dropped 状态恢复流程。"""

    client = TestClient(app)
    creator_id = "creator_reengagement_review"
    _create_creator(client, creator_id)
    client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "No thanks, not interested.", "run_agent": True},
    )

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "I changed my mind and am interested in collaborating.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"]["processing_status"] == "need_ai_review"

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status is None
        task = db.scalar(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator_id)
            .where(FollowupTask.task_type == "reengagement_review")
        )
        assert task is None


def test_campaign_brief_fields_are_available_to_product_context():
    """时间线、交付物和预算指引应能随产品档案写入并返回。"""

    client = TestClient(app)
    response = client.post(
        "/api/followup-agent/products",
        json={
            "id": "product_campaign_brief",
            "product_type": "campaign brief type",
            "name": "Campaign Brief Product",
            "summary": "Synthetic product.",
            "campaign_timeline": "Content due within 14 days after product delivery.",
            "campaign_deliverables": "One short video and one product link.",
            "budget_guidance": "Budget is confirmed by BD before approval.",
        },
    )
    assert response.status_code == 201, response.text
    product = response.json()["product"]
    assert product["campaign_timeline"] == "Content due within 14 days after product delivery."
    assert product["campaign_deliverables"] == "One short video and one product link."
    assert product["budget_guidance"] == "Budget is confirmed by BD before approval."


def test_detail_request_with_missing_campaign_brief_requires_human_and_names_missing_fields(monkeypatch):
    """达人索要合作资料而档案缺失时，系统必须转人工而非要求模型编造。"""

    client = TestClient(app)
    creator_id = "creator_missing_campaign_brief"
    _create_creator(client, creator_id)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    monkeypatch.setattr(
        services,
        "call_siliconflow_json",
        lambda system_prompt, user_prompt: pytest.fail("Missing campaign brief must not call the provider"),
    )
    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": creator_id,
            "body": "Could you send campaign details, timeline, deliverables, and budget?",
            "run_agent": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    output = run["output"]
    assert run["llm_status"] == "skipped"
    assert run["execution_status"] == "succeeded"
    assert run["block_reason"] == "context_insufficient"
    assert output["next_action"] == "prepare_campaign_brief"
    assert "missing_campaign_timeline" in output["warnings"]
    assert "missing_campaign_deliverables" in output["warnings"]
    assert "missing_budget_guidance" in output["warnings"]


def test_explicit_opt_out_marks_do_not_contact_pending_confirmation():
    client = TestClient(app)
    creator_id = "creator_opt_out"
    _create_creator(client, creator_id)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe and remove me.", "run_agent": False},
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        assert hasattr(models, "DoNotContactConfirmation")
        confirmation_model = models.DoNotContactConfirmation
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status is None
        assert creator.do_not_contact_status == "pending_confirmation"
        assert creator.do_not_contact_reason == "explicit_opt_out"
        assert creator.do_not_contact_requested_at is not None
        assert db.scalar(select(func.count()).select_from(FollowupTask).where(FollowupTask.creator_id == creator_id)) == 0
        confirmations = list(
            db.scalars(
                select(confirmation_model)
                .where(confirmation_model.creator_id == creator_id)
                .where(confirmation_model.status == "pending_confirmation")
            ).all()
        )
        assert len(confirmations) == 1
        assert confirmations[0].reason == "explicit_opt_out"
        assert confirmations[0].inbound_reply_id is not None
        assert confirmations[0].reviewed_by is None
        assert confirmations[0].reviewed_at is None

    queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["decision_available"] is False


def test_human_can_confirm_pending_dnc_without_creating_an_outbound_action():
    client = TestClient(app)
    creator_id = "creator_confirm_dnc"
    _create_creator(client, creator_id)

    opt_out = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe me from all future messages.", "run_agent": True},
    )
    assert opt_out.status_code == 200, opt_out.text

    queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert queue.status_code == 200, queue.text
    confirmation_id = queue.json()["items"][0]["dnc_confirmation"]["id"]

    confirmed = client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/approve",
        json={"actor_id": "demo_operator"},
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["confirmation"]["status"] == "confirmed"
    assert payload["confirmation"]["reviewed_by"] == "demo_operator"
    assert payload["confirmation"]["reviewed_at"] is not None
    assert payload["creator"]["do_not_contact_status"] == "confirmed"
    assert payload["reply"]["processing_status"] == "reviewed"

    assert client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation").json()["total"] == 0
    assert client.get(f"/api/followup-agent/review-items/{opt_out.json()['reply']['id']}").status_code == 409
    assert client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/approve",
        json={"actor_id": "demo_operator"},
    ).status_code == 409

    later_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Could you share campaign details?", "run_agent": True},
    )
    assert later_reply.status_code == 200, later_reply.text
    assert later_reply.json()["reply"]["processing_status"] == "dnc_blocked"
    assert later_reply.json()["run"] is None
    assert client.get(f"/api/followup-agent/outbound-instructions?creator_id={creator_id}").json()["total"] == 0

    with SessionLocal() as db:
        event = db.scalar(
            select(CreatorOutreachEvent)
            .where(CreatorOutreachEvent.creator_id == creator_id)
            .where(CreatorOutreachEvent.event_type == "dnc_confirmed_by_human")
        )
        assert event is not None
        assert json.loads(event.metadata_json or "{}") == {
            "actor_id": "demo_operator",
            "dnc_confirmation_id": confirmation_id,
            "inbound_reply_id": opt_out.json()["reply"]["id"],
        }


def test_human_can_reject_pending_dnc_and_requeue_it_for_standard_review():
    client = TestClient(app)
    creator_id = "creator_reject_dnc"
    _create_creator(client, creator_id)
    prior_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "I am interested in hearing more.", "run_agent": False},
    )
    assert prior_reply.status_code == 200, prior_reply.text
    opt_out = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe me from future messages.", "run_agent": False},
    )
    assert opt_out.status_code == 200, opt_out.text

    queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert queue.status_code == 200, queue.text
    confirmation_id = queue.json()["items"][0]["dnc_confirmation"]["id"]

    rejected = client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/reject",
        json={"actor_id": "demo_operator"},
    )
    assert rejected.status_code == 200, rejected.text
    payload = rejected.json()
    assert payload["confirmation"]["status"] == "rejected"
    assert payload["confirmation"]["reviewed_by"] == "demo_operator"
    assert payload["creator"]["do_not_contact_status"] == "none"
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert payload["reply"]["reply_category"] == "unclear"
    assert payload["reply"]["classification_reason"] == "human_rejected_dnc_confirmation"
    assert payload["run"]["execution_status"] == "queued"
    assert payload["run"]["created_by"] == "demo_operator"

    dnc_queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert dnc_queue.status_code == 200, dnc_queue.text
    assert dnc_queue.json()["total"] == 0
    detail = client.get(f"/api/followup-agent/review-items/{opt_out.json()['reply']['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["item"]["review_type"] == "generation_pending"
    assert detail.json()["item"]["decision_available"] is False
    assert detail.json()["runs"][-1]["id"] == payload["run"]["id"]
    assert client.get(f"/api/followup-agent/outbound-instructions?creator_id={creator_id}").json()["total"] == 0

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.do_not_contact_reason is None
        assert creator.do_not_contact_requested_at is None
        blocked_task = db.scalar(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator_id)
            .where(FollowupTask.task_type == "reply_followup_1")
        )
        assert blocked_task is not None
        assert blocked_task.status == "blocked_dnc_rejected"
        event = db.scalar(
            select(CreatorOutreachEvent)
            .where(CreatorOutreachEvent.creator_id == creator_id)
            .where(CreatorOutreachEvent.event_type == "dnc_rejected_by_human")
        )
        assert event is not None
        metadata = json.loads(event.metadata_json or "{}")
        assert metadata["actor_id"] == "demo_operator"
        assert metadata["dnc_confirmation_id"] == confirmation_id
        assert metadata["original_reply_category"] == "not_interested"
        assert metadata["queued_run_id"] == payload["run"]["id"]


def test_human_can_retry_a_model_failure_as_a_new_audited_run():
    client = TestClient(app)
    creator_id = "creator_retry_model_failure"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    reply_id = simulated.json()["reply"]["id"]
    failed_run_id = simulated.json()["run"]["id"]

    with SessionLocal() as db:
        failed_run = db.get(AgentFollowupRun, failed_run_id)
        assert failed_run is not None
        failed_run.execution_status = "failed"
        failed_run.llm_status = "validation_failed"
        failed_run.output_json = json.dumps({"raw_output": "{\"reply_category\": \"interested\"}"})
        failed_run.validation_error = "suggested_reply: Field required"
        failed_run.error_summary = "Synthetic validation failure."
        failed_run.finished_at = datetime.utcnow()
        db.commit()

    retry = client.post(
        f"/api/followup-agent/review-items/{reply_id}/retry",
        json={"actor_id": "demo_operator"},
    )
    assert retry.status_code == 200, retry.text
    payload = retry.json()
    assert payload["run"]["id"] != failed_run_id
    assert payload["run"]["execution_status"] == "queued"
    assert payload["run"]["created_by"] == "demo_operator"
    assert client.post(
        f"/api/followup-agent/review-items/{reply_id}/retry",
        json={"actor_id": "demo_operator"},
    ).status_code == 409

    with SessionLocal() as db:
        runs = list(
            db.scalars(
                select(AgentFollowupRun)
                .where(AgentFollowupRun.inbound_reply_id == reply_id)
                .order_by(AgentFollowupRun.created_at.asc(), AgentFollowupRun.id.asc())
            ).all()
        )
        assert len(runs) == 2
        assert runs[0].id == failed_run_id
        assert runs[0].execution_status == "failed"
        assert runs[1].id == payload["run"]["id"]
        event = db.scalar(
            select(CreatorOutreachEvent)
            .where(CreatorOutreachEvent.creator_id == creator_id)
            .where(CreatorOutreachEvent.event_type == "agent_retry_requested_by_human")
        )
        assert event is not None
        assert json.loads(event.metadata_json or "{}") == {
            "actor_id": "demo_operator",
            "inbound_reply_id": reply_id,
            "failed_run_id": failed_run_id,
            "queued_run_id": payload["run"]["id"],
        }
    assert client.get(f"/api/followup-agent/outbound-instructions?creator_id={creator_id}").json()["total"] == 0


def test_human_retry_translates_active_run_unique_conflict_to_409(monkeypatch):
    """并发重试由唯一索引裁决时，接口必须返回业务冲突而非 500。"""

    client = TestClient(app)
    creator_id = "creator_retry_unique_conflict"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    reply_id = simulated.json()["reply"]["id"]
    failed_run_id = simulated.json()["run"]["id"]

    with SessionLocal() as db:
        failed_run = db.get(AgentFollowupRun, failed_run_id)
        assert failed_run is not None
        failed_run.execution_status = "failed"
        failed_run.llm_status = "validation_failed"
        failed_run.output_json = json.dumps({"raw_output": "{}"})
        failed_run.validation_error = "suggested_reply: Field required"
        failed_run.error_summary = "Synthetic validation failure."
        failed_run.finished_at = datetime.utcnow()
        db.commit()

    def raise_active_run_unique_conflict(*args, **kwargs):
        assert kwargs["reject_if_active"] is True
        raise IntegrityError(
            "INSERT INTO agent_followup_runs ...",
            {},
            Exception("uq_agent_followup_runs_active_reply"),
        )

    monkeypatch.setattr(
        importlib.import_module("app.main"),
        "enqueue_followup_run",
        raise_active_run_unique_conflict,
    )
    retry = client.post(
        f"/api/followup-agent/review-items/{reply_id}/retry",
        json={"actor_id": "demo_operator"},
    )
    assert retry.status_code == 409
    assert retry.json()["detail"] == "agent retry is already queued"

    with SessionLocal() as db:
        assert db.scalar(
            select(func.count()).select_from(AgentFollowupRun).where(AgentFollowupRun.inbound_reply_id == reply_id)
        ) == 1
        assert db.scalar(
            select(func.count())
            .select_from(CreatorOutreachEvent)
            .where(CreatorOutreachEvent.creator_id == creator_id)
            .where(CreatorOutreachEvent.event_type == "agent_retry_requested_by_human")
        ) == 0


def test_explicit_opt_out_blocks_existing_normal_followup_task():
    """DNC 进入待确认时，既有普通外联待办必须立即停止，不能继续引导人工联系。"""

    client = TestClient(app)
    creator_id = "creator_opt_out_blocks_task"
    _create_creator(client, creator_id)
    normal_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": False},
    )
    assert normal_reply.status_code == 200, normal_reply.text

    with SessionLocal() as db:
        task = db.scalar(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator_id)
            .where(FollowupTask.task_type == "reply_followup_1")
        )
        assert task is not None
        assert task.status == "open"
        assert task.reason == "Creator replied; follow up now."

    opt_out = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe and remove me.", "run_agent": True},
    )
    assert opt_out.status_code == 200, opt_out.text
    assert opt_out.json()["reply"]["processing_status"] == "need_ai_review"

    with SessionLocal() as db:
        task = db.scalar(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator_id)
            .where(FollowupTask.task_type == "reply_followup_1")
        )
        assert task is not None
        assert task.status == "blocked_dnc_pending"
        assert task.reason == "Blocked: creator requested do not contact; confirmation is pending."
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.do_not_contact_status == "pending_confirmation"

    queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["reply"]["id"] == opt_out.json()["reply"]["id"]


def test_repeated_explicit_opt_out_keeps_one_pending_dnc_confirmation():
    """同一达人再次明确退订时，DNC 审核流水不应出现重复待确认记录。"""

    client = TestClient(app)
    creator_id = "creator_repeated_opt_out"
    _create_creator(client, creator_id)

    first = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe me.", "run_agent": True},
    )
    second = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Remove me from future contact.", "run_agent": True},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    with SessionLocal() as db:
        assert hasattr(models, "DoNotContactConfirmation")
        confirmation_model = models.DoNotContactConfirmation
        confirmations = list(
            db.scalars(
                select(confirmation_model)
                .where(confirmation_model.creator_id == creator_id)
                .where(confirmation_model.status == "pending_confirmation")
            ).all()
        )
        assert len(confirmations) == 1
        replies = list(db.scalars(select(InboundReply).where(InboundReply.creator_id == creator_id)).all())
        assert sum(reply.processing_status == "need_ai_review" for reply in replies) == 1
        assert sum(reply.processing_status == "dnc_blocked" for reply in replies) == 1


def test_decline_and_bounce_do_not_create_simulated_outbound_instruction():
    """终态待审和退信均不应预先创建可被误解为外发动作的指令。"""

    client = TestClient(app)
    _create_creator(client, "creator_simulated_decline")
    declined = client.post("/api/followup-agent/simulate-reply", json={"creator_id": "creator_simulated_decline", "body": "Please unsubscribe me.", "run_agent": True})
    repeated = client.post("/api/followup-agent/simulate-reply", json={"creator_id": "creator_simulated_decline", "body": "No thanks, not interested.", "run_agent": True})
    _create_creator(client, "creator_simulated_bounce")
    bounced = client.post("/api/followup-agent/simulate-reply", json={"creator_id": "creator_simulated_bounce", "body": "Delivery failed, invalid address.", "run_agent": True})
    assert declined.status_code == 200 and repeated.status_code == 200 and bounced.status_code == 200

    instructions = client.get("/api/followup-agent/outbound-instructions?creator_id=creator_simulated_decline")
    assert instructions.status_code == 200, instructions.text
    assert instructions.json()["total"] == 0
    assert client.get("/api/followup-agent/outbound-instructions?creator_id=creator_simulated_bounce").json()["total"] == 0


def test_product_api_creates_updates_and_rejects_duplicate_type():
    client = TestClient(app)
    payload = _product_payload(id="product_travel", product_type="travel care")

    created = client.post("/api/followup-agent/products", json=payload)
    duplicate = client.post("/api/followup-agent/products", json={**payload, "id": "product_travel_duplicate"})
    replaced = client.put(
        "/api/followup-agent/products/product_travel",
        json=_product_payload(
            id="ignored_by_path",
            product_type="travel care",
            name="Updated Travel Care",
            notes=None,
        ),
    )
    patched = client.patch(
        "/api/followup-agent/products/product_travel",
        json={"summary": "Patched summary."},
    )

    assert created.status_code == 201, created.text
    assert duplicate.status_code == 409
    assert replaced.status_code == 200, replaced.text
    assert patched.status_code == 200, patched.text
    assert hasattr(models, "Product")
    with SessionLocal() as db:
        product = db.get(models.Product, "product_travel")
        assert product is not None
        assert product.name == "Updated Travel Care"
        assert product.summary == "Patched summary."
        assert product.notes is None


def test_product_context_is_added_to_run_and_previous_inbound_reply_is_preserved():
    client = TestClient(app)
    creator_id = "creator_product_context"
    _create_creator(client, creator_id)

    previous = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Could you share the details?", "run_agent": False},
    )
    current = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert previous.status_code == 200, previous.text
    assert current.status_code == 200, current.text
    context = _process_response_run(client, current)["context"]
    assert context["product"]["name"] == "Baby Care Starter"
    assert context["product"]["selling_points"] == ["gentle formula", "easy daily use"]
    assert context["recent_inbound_replies"][0]["id"] == previous.json()["reply"]["id"]


def test_missing_or_inactive_product_context_requires_manual_review():
    client = TestClient(app)
    missing_creator_id = "creator_missing_catalog_product"
    _create_creator(client, missing_creator_id, recommended_product_type="unknown type")

    missing_response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": missing_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert missing_response.status_code == 200, missing_response.text
    assert missing_response.json()["reply"]["processing_status"] == "need_ai_review"
    assert "missing_product_context" in _process_response_run(client, missing_response)["output"]["warnings"]

    inactive_product = client.post(
        "/api/followup-agent/products",
        json=_product_payload(id="product_inactive", product_type="inactive care", is_active=False),
    )
    assert inactive_product.status_code == 201, inactive_product.text
    inactive_creator_id = "creator_inactive_catalog_product"
    _create_creator(client, inactive_creator_id, recommended_product_type="inactive care")
    inactive_response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": inactive_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert inactive_response.status_code == 200, inactive_response.text
    assert inactive_response.json()["reply"]["processing_status"] == "need_ai_review"
    assert "missing_product_context" in _process_response_run(client, inactive_response)["output"]["warnings"]


def test_product_put_and_patch_return_404_for_missing_product():
    client = TestClient(app)
    put_response = client.put(
        "/api/followup-agent/products/product_missing",
        json=_product_payload(id="ignored", product_type="missing type"),
    )
    patch_response = client.patch(
        "/api/followup-agent/products/product_missing",
        json={"name": "Missing"},
    )
    assert put_response.status_code == 404
    assert patch_response.status_code == 404


def test_prompt_package_masks_contact_data_detects_chinese_and_respects_budget():
    prompts = importlib.import_module("app.prompts")
    context = {
        "reply_category": "interested",
        "product": {
            "name": "Baby Care Starter",
            "summary": "A product page is https://product.example.com/private.",
            "selling_points": ["gentle formula"],
            "target_audience": "Parents",
            "collaboration_requirements": "One video.",
            "forbidden_claims": ["No cure claims"],
            "notes": None,
        },
        "creator": {
            "handle": "creator_handle",
            "display_name": "Creator Name",
            "email": "creator@example.com",
            "profile_url": "https://social.example.com/creator",
            "bio": "Parent creator",
            "followers_count": 5000,
            "recommendation_reason": "Audience fit",
            "recommended_product_type": "baby care",
            "recommended_collab_type": "affiliate",
        },
        "inbound_reply": {
            "subject": "合作咨询",
            "body": "我有兴趣，请联系 hidden@example.com，详情见 https://private.example.com。" + "甲" * 13000,
        },
        "recent_inbound_replies": [{"body": "Earlier reply from history@example.com"}],
        "recent_outreach_emails": [{"subject": "Campaign", "body": "Visit https://outreach.example.com"}],
        "recent_events": [{"event_type": "pending_followup", "note": "Previous event"}],
        "open_followup_tasks": [{"task_type": "reply_followup_1", "reason": "Follow up"}],
    }

    package = prompts.build_prompt_package(context)
    assert package.prompt_version == "reply_followup_v2"
    assert package.reply_language == "zh"
    assert len(package.rendered_prompt) <= 12000
    assert "[内容已省略]" in package.rendered_prompt
    assert "hidden@example.com" not in package.rendered_prompt
    assert "creator@example.com" not in package.rendered_prompt
    assert "https://private.example.com" not in package.rendered_prompt
    assert "https://social.example.com/creator" not in package.rendered_prompt
    assert "我有兴趣" in package.rendered_prompt


def test_agent_run_persists_redacted_prompt_package():
    client = TestClient(app)
    creator_id = "creator_prompt_audit"
    _create_creator(
        client,
        creator_id,
        profile_url="https://social.example.com/private-profile",
        email="creator-audit@example.com",
    )

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": creator_id,
            "from_email": "inbound-audit@example.com",
            "body": "Sounds interesting. Contact hidden-audit@example.com at https://private.example.com.",
            "run_agent": True,
        },
    )
    assert response.status_code == 200, response.text
    run = _process_response_run(client, response)
    assert run["prompt_version"] == "reply_followup_v2"
    assert run["rendered_prompt"]
    assert "inbound-audit@example.com" not in run["rendered_prompt"]
    assert "creator-audit@example.com" not in run["rendered_prompt"]
    assert "https://private.example.com" not in run["rendered_prompt"]
    assert "https://social.example.com/private-profile" not in run["rendered_prompt"]


def test_post_creator_returns_conflict_when_creator_already_exists():
    client = TestClient(app)
    creator_id = "creator_duplicate_create"
    _create_creator(client, creator_id)

    response = client.post(
        "/api/followup-agent/creators",
        json={"id": creator_id, "handle": "another_handle"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "creator already exists"


def test_put_creator_replaces_full_profile_and_can_clear_nullable_fields():
    client = TestClient(app)
    creator_id = "creator_put_replace"
    _create_creator(
        client,
        creator_id,
        display_name="Original Name",
        bio="Original bio",
        profile_url="https://example.com/original",
    )

    response = client.put(
        f"/api/followup-agent/creators/{creator_id}",
        json=_creator_replace_payload(
            handle="replaced_handle",
            display_name=None,
            profile_url=None,
            bio=None,
            email="replaced@example.com",
            recommendation_reason="Replaced profile.",
        ),
    )
    assert response.status_code == 200, response.text

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.handle == "replaced_handle"
        assert creator.display_name is None
        assert creator.profile_url is None
        assert creator.bio is None
        assert creator.email == "replaced@example.com"
        assert creator.recommendation_reason == "Replaced profile."


def test_patch_creator_preserves_omitted_fields_and_clears_explicit_null():
    client = TestClient(app)
    creator_id = "creator_patch_profile"
    _create_creator(
        client,
        creator_id,
        display_name="Original Name",
        bio="Original bio",
        profile_url="https://example.com/original",
        email="original@example.com",
    )

    first_patch = client.patch(
        f"/api/followup-agent/creators/{creator_id}",
        json={"display_name": "Patched Name"},
    )
    assert first_patch.status_code == 200, first_patch.text
    second_patch = client.patch(
        f"/api/followup-agent/creators/{creator_id}",
        json={"bio": None},
    )
    assert second_patch.status_code == 200, second_patch.text

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.display_name == "Patched Name"
        assert creator.bio is None
        assert creator.profile_url == "https://example.com/original"
        assert creator.email == "original@example.com"


def test_put_and_patch_return_404_for_missing_creator():
    client = TestClient(app)
    creator_id = "creator_missing_update"

    put_response = client.put(
        f"/api/followup-agent/creators/{creator_id}",
        json=_creator_replace_payload(handle="missing_handle"),
    )
    patch_response = client.patch(
        f"/api/followup-agent/creators/{creator_id}",
        json={"display_name": "Missing"},
    )
    assert put_response.status_code == 404
    assert patch_response.status_code == 404


def test_get_reply_returns_404_for_unknown_id():
    init_db()
    client = TestClient(app)
    response = client.get("/api/followup-agent/replies/missing_reply")
    assert response.status_code == 404
    assert response.json()["detail"] == "inbound reply not found"


def test_duplicate_reply_is_idempotent_and_does_not_repeat_side_effects():
    init_db()
    client = TestClient(app)
    creator_id = "creator_duplicate"
    _create_creator(client, creator_id)
    request_body = {
        "creator_id": creator_id,
        "from_email": "duplicate@example.com",
        "to_email": "bd@example.com",
        "subject": "Re: Campaign",
        "body": "Sounds interesting.",
        "run_agent": True,
    }

    first = client.post("/api/followup-agent/simulate-reply", json=request_body)
    second = client.post("/api/followup-agent/simulate-reply", json=request_body)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["reply"]["id"] == first.json()["reply"]["id"]
    assert second.json()["run"]["id"] == first.json()["run"]["id"]
    assert first.json()["reply"]["channel"] == "simulation"
    assert first.json()["reply"]["external_message_id"].startswith("simulation:")
    assert first.json()["reply"]["external_message_id"] == second.json()["reply"]["external_message_id"]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InboundReply).where(InboundReply.creator_id == creator_id)) == 1
        assert db.scalar(
            select(func.count()).select_from(CreatorOutreachEvent).where(CreatorOutreachEvent.creator_id == creator_id)
        ) == 1
        assert db.scalar(select(func.count()).select_from(FollowupTask).where(FollowupTask.creator_id == creator_id)) == 1
        assert db.scalar(
            select(func.count()).select_from(AgentFollowupRun).where(AgentFollowupRun.creator_id == creator_id)
        ) == 1


def test_changed_subject_creates_a_distinct_reply():
    init_db()
    client = TestClient(app)
    creator_id = "creator_distinct"
    _create_creator(client, creator_id)
    base = {"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": False}

    first = client.post("/api/followup-agent/simulate-reply", json={**base, "subject": "Re: Campaign A"})
    second = client.post("/api/followup-agent/simulate-reply", json={**base, "subject": "Re: Campaign B"})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is False
    assert first.json()["reply"]["id"] != second.json()["reply"]["id"]


def test_duplicate_reply_can_be_run_later_without_creating_a_second_reply():
    init_db()
    client = TestClient(app)
    creator_id = "creator_duplicate_later_run"
    _create_creator(client, creator_id)
    request_body = {"creator_id": creator_id, "subject": "Re: Campaign", "body": "Sounds interesting."}

    first = client.post("/api/followup-agent/simulate-reply", json={**request_body, "run_agent": False})
    second = client.post("/api/followup-agent/simulate-reply", json={**request_body, "run_agent": True})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["duplicate"] is False
    assert first.json()["run"] is None
    assert second.json()["duplicate"] is True
    assert second.json()["reply"]["id"] == first.json()["reply"]["id"]
    assert second.json()["run"] is not None

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(InboundReply).where(InboundReply.creator_id == creator_id)) == 1
        assert db.scalar(
            select(func.count()).select_from(AgentFollowupRun).where(AgentFollowupRun.creator_id == creator_id)
        ) == 1


def test_real_message_external_id_is_unique_while_identical_content_can_coexist():
    init_db()
    client = TestClient(app)
    creator_id = "creator_external_message_id"
    _create_creator(client, creator_id)
    values = {
        "department_code": "cross_border",
        "creator_id": creator_id,
        "direction": "inbound",
        "channel": "email",
        "from_email": "",
        "to_email": "",
        "subject": "",
        "body": "Same body",
        "body_format": "plain",
        "message_at": datetime.utcnow(),
    }

    with SessionLocal() as db:
        db.add(InboundReply(id="ir_external_first", external_message_id="provider_message_1", **values))
        db.commit()
        db.add(InboundReply(id="ir_external_second", external_message_id="provider_message_2", **values))
        db.commit()
        db.add(InboundReply(id="ir_external_duplicate", external_message_id="provider_message_1", **values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(func.count()).select_from(InboundReply).where(InboundReply.creator_id == creator_id)) == 2


def test_inbound_reply_and_active_run_database_constraints():
    init_db()
    client = TestClient(app)
    creator_id = "creator_database_constraints"
    _create_creator(client, creator_id)
    values = {
        "department_code": "cross_border",
        "creator_id": creator_id,
        "direction": "inbound",
        "channel": "email",
        "from_email": "creator@example.com",
        "to_email": "bd@example.com",
        "subject": "Re: Campaign",
        "body": "Same body",
        "body_format": "plain",
        "message_at": datetime.utcnow(),
    }

    with SessionLocal() as db:
        db.add(InboundReply(id="ir_external_missing", external_message_id=None, **values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        reply = InboundReply(id="ir_constraints", external_message_id="provider_message_constraints", **values)
        db.add(reply)
        db.commit()

        db.add(
            AgentFollowupRun(
                id="afr_orphan_creator",
                department_code="cross_border",
                creator_id="missing_creator",
                inbound_reply_id=reply.id,
                reply_category="interested",
                llm_status="pending",
                execution_status="queued",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            AgentFollowupRun(
                id="afr_orphan_reply",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id="missing_reply",
                reply_category="interested",
                llm_status="pending",
                execution_status="queued",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            AgentFollowupRun(
                id="afr_active_first",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id=reply.id,
                reply_category="interested",
                llm_status="pending",
                execution_status="queued",
            )
        )
        db.commit()

        db.add(
            AgentFollowupRun(
                id="afr_active_second",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id=reply.id,
                reply_category="interested",
                llm_status="pending",
                execution_status="running",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_audited_reply_and_creator_cannot_be_deleted():
    init_db()
    client = TestClient(app)
    creator_id = "creator_audit_restrict"
    _create_creator(client, creator_id)
    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe me.", "run_agent": False},
    )
    assert response.status_code == 200, response.text
    reply_id = response.json()["reply"]["id"]

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(delete(InboundReply).where(InboundReply.id == reply_id))
            db.commit()
        db.rollback()

    with SessionLocal() as db:
        with pytest.raises(IntegrityError):
            db.execute(delete(Creator).where(Creator.id == creator_id))
            db.commit()
        db.rollback()


def test_human_review_audit_records_require_existing_run_and_cannot_be_rewritten():
    """审核决定与导出快照必须受外键和唯一约束保护，保证留痕可追溯。"""

    init_db()
    client = TestClient(app)
    creator_id = "creator_human_review_audit"
    _create_creator(client, creator_id)
    reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": False},
    )
    assert reply.status_code == 200, reply.text
    reply_id = reply.json()["reply"]["id"]

    with SessionLocal() as db:
        run = AgentFollowupRun(
            id="afr_human_review_audit",
            department_code="cross_border",
            creator_id=creator_id,
            inbound_reply_id=reply_id,
            reply_category="interested",
            llm_status="succeeded",
            execution_status="succeeded",
        )
        db.add(run)
        db.commit()

        db.add(
            HumanReviewDecision(
                id="hrd_missing_run",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id=reply_id,
                agent_followup_run_id="missing_run",
                outcome="approve_draft",
                final_draft="Thank you for your interest.",
                actor_id="reviewer_1",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        decision = HumanReviewDecision(
            id="hrd_human_review_audit",
            department_code="cross_border",
            creator_id=creator_id,
            inbound_reply_id=reply_id,
            agent_followup_run_id=run.id,
            outcome="approve_draft",
            final_draft="Thank you for your interest.",
            actor_id="reviewer_1",
        )
        db.add(decision)
        db.commit()

        db.add(
            HumanReviewDecision(
                id="hrd_duplicate_run",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id=reply_id,
                agent_followup_run_id=run.id,
                outcome="close_without_draft",
                actor_id="reviewer_2",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 即使绕过 API 为同一回复直接插入新的已完成 run，数据库仍必须禁止第二个最终决定。
        second_run = AgentFollowupRun(
            id="afr_human_review_audit_second",
            department_code="cross_border",
            creator_id=creator_id,
            inbound_reply_id=reply_id,
            reply_category="interested",
            llm_status="succeeded",
            execution_status="succeeded",
        )
        db.add(second_run)
        db.commit()
        db.add(
            HumanReviewDecision(
                id="hrd_duplicate_reply",
                department_code="cross_border",
                creator_id=creator_id,
                inbound_reply_id=reply_id,
                agent_followup_run_id=second_run.id,
                outcome="close_without_draft",
                actor_id="reviewer_2",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(
            DraftExportRecord(
                id="der_human_review_audit",
                department_code="cross_border",
                human_review_decision_id=decision.id,
                creator_id=creator_id,
                inbound_reply_id=reply_id,
                exported_content="Thank you for your interest.",
                actor_id="operator_1",
            )
        )
        db.commit()

        with pytest.raises(IntegrityError):
            db.execute(delete(HumanReviewDecision).where(HumanReviewDecision.id == decision.id))
            db.commit()
        db.rollback()

        with pytest.raises(IntegrityError):
            db.execute(delete(AgentFollowupRun).where(AgentFollowupRun.id == run.id))
            db.commit()
        db.rollback()


def test_standard_human_review_queue_approves_draft_without_advancing_creator_status():
    """普通草稿必须由人工决定，且批准草稿不等于自动推进达人业务状态。"""

    client = TestClient(app)
    creator_id = "creator_standard_human_review"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    reply_id = simulated.json()["reply"]["id"]
    run = _process_response_run(client, simulated)

    queue = client.get("/api/followup-agent/review-queue?department_code=cross_border")
    assert queue.status_code == 200, queue.text
    item = next(row for row in queue.json()["items"] if row["reply"]["id"] == reply_id)
    assert item["review_type"] == "standard"
    assert item["decision_available"] is True
    assert item["run"]["id"] == run["id"]

    invalid = client.post(
        "/api/followup-agent/review-decisions",
        json={"agent_followup_run_id": run["id"], "outcome": "approve_draft", "actor_id": "reviewer_1"},
    )
    assert invalid.status_code == 422

    approved = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "approve_draft",
            "final_draft": "Thank you for your interest. Here are the campaign details.",
            "note": "Approved after checking the product brief.",
            "actor_id": "reviewer_1",
        },
    )
    assert approved.status_code == 201, approved.text
    payload = approved.json()
    assert payload["reply"]["processing_status"] == "reviewed"
    assert payload["decision"]["outcome"] == "approve_draft"
    assert payload["decision"]["final_draft"].startswith("Thank you for your interest")

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status is None
        assert db.scalar(select(func.count()).select_from(HumanReviewDecision)) == 1

    repeated = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "approve_draft",
            "final_draft": "A second decision must fail.",
            "actor_id": "reviewer_2",
        },
    )
    assert repeated.status_code == 409

    queue_after_review = client.get("/api/followup-agent/review-queue")
    assert queue_after_review.status_code == 200, queue_after_review.text
    approved_item = next(row for row in queue_after_review.json()["items"] if row["reply"]["id"] == reply_id)
    assert approved_item["review_type"] == "approved_draft"
    assert approved_item["decision_available"] is False
    assert approved_item["decision"]["id"] == payload["decision"]["id"]


def test_operator_workbench_queue_lists_generation_pending_and_approved_drafts():
    """工作台应分别展示 Agent 正在生成的回复和可人工交接的已批准草稿。"""

    client = TestClient(app)

    approved_creator_id = "creator_workbench_approved_draft"
    _create_creator(client, approved_creator_id)
    approved_source = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": approved_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert approved_source.status_code == 200, approved_source.text
    approved_reply_id = approved_source.json()["reply"]["id"]
    approved_run = _process_response_run(client, approved_source)
    approved = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": approved_run["id"],
            "outcome": "approve_draft",
            "final_draft": "Approved draft for manual handoff only.",
            "actor_id": "reviewer_workbench",
        },
    )
    assert approved.status_code == 201, approved.text
    decision_id = approved.json()["decision"]["id"]

    queued_creator_id = "creator_workbench_generation_pending"
    _create_creator(client, queued_creator_id)
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": queued_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert queued.status_code == 200, queued.text
    queued_reply_id = queued.json()["reply"]["id"]
    assert queued.json()["run"]["execution_status"] == "queued"

    queue = client.get("/api/followup-agent/review-queue")
    assert queue.status_code == 200, queue.text
    items_by_reply_id = {item["reply"]["id"]: item for item in queue.json()["items"]}
    generation_item = items_by_reply_id[queued_reply_id]
    assert generation_item["review_type"] == "generation_pending"
    assert generation_item["decision_available"] is False
    assert generation_item["run"]["execution_status"] == "queued"
    approved_item = items_by_reply_id[approved_reply_id]
    assert approved_item["review_type"] == "approved_draft"
    assert approved_item["decision_available"] is False
    assert approved_item["decision"]["id"] == decision_id
    assert approved_item["decision"]["final_draft"] == "Approved draft for manual handoff only."

    for review_type, reply_id in (("generation_pending", queued_reply_id), ("approved_draft", approved_reply_id)):
        filtered = client.get(f"/api/followup-agent/review-queue?review_type={review_type}")
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["reply"]["id"] == reply_id

    approved_detail = client.get(f"/api/followup-agent/review-items/{approved_reply_id}")
    assert approved_detail.status_code == 200, approved_detail.text
    assert approved_detail.json()["item"]["review_type"] == "approved_draft"
    assert approved_detail.json()["item"]["decision"]["id"] == decision_id


def test_operator_workbench_reply_ready_filter_combines_pending_and_locked_drafts():
    """“人工回复草稿”聚合只读筛选应同时返回待审核项和已锁定的批准草稿。"""

    client = TestClient(app)

    pending_creator_id = "creator_workbench_reply_ready_pending"
    _create_creator(client, pending_creator_id)
    pending_source = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": pending_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert pending_source.status_code == 200, pending_source.text
    pending_reply_id = pending_source.json()["reply"]["id"]
    pending_run = _process_response_run(client, pending_source)
    assert pending_run["execution_status"] == "succeeded"

    approved_creator_id = "creator_workbench_reply_ready_approved"
    _create_creator(client, approved_creator_id)
    approved_source = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": approved_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert approved_source.status_code == 200, approved_source.text
    approved_reply_id = approved_source.json()["reply"]["id"]
    approved_run = _process_response_run(client, approved_source)
    approved = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": approved_run["id"],
            "outcome": "approve_draft",
            "final_draft": "Locked draft for manual handoff.",
            "actor_id": "reviewer_workbench",
        },
    )
    assert approved.status_code == 201, approved.text

    reply_ready = client.get("/api/followup-agent/review-queue?review_type=reply_ready")
    assert reply_ready.status_code == 200, reply_ready.text
    assert reply_ready.json()["total"] == 2
    items_by_reply_id = {item["reply"]["id"]: item for item in reply_ready.json()["items"]}
    assert items_by_reply_id[pending_reply_id]["review_type"] == "standard"
    assert items_by_reply_id[pending_reply_id]["decision_available"] is True
    assert items_by_reply_id[approved_reply_id]["review_type"] == "approved_draft"
    assert items_by_reply_id[approved_reply_id]["decision_available"] is False
    assert items_by_reply_id[approved_reply_id]["decision"]["final_draft"] == "Locked draft for manual handoff."

    assert client.get("/api/followup-agent/review-queue?review_type=standard").json()["total"] == 1
    assert client.get("/api/followup-agent/review-queue?review_type=approved_draft").json()["total"] == 1


def test_review_queue_separates_model_failures_from_standard_and_terminal_items(monkeypatch):
    client = TestClient(app)

    standard_creator_id = "creator_review_queue_standard"
    _create_creator(client, standard_creator_id)
    standard = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": standard_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert standard.status_code == 200, standard.text
    standard_run = _process_response_run(client, standard)
    assert standard_run["execution_status"] == "succeeded"

    failure_creator_id = "creator_review_queue_model_failure"
    _create_creator(client, failure_creator_id)
    invalid_output = json.dumps({"reply_category": "interested", "confidence": 0.9})
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context, prompt: (invalid_output, "mocked"))
    model_failure = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": failure_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert model_failure.status_code == 200, model_failure.text
    failure_run = _process_response_run(client, model_failure)
    assert failure_run["execution_status"] == "failed"
    assert failure_run["llm_status"] == "validation_failed"

    decline_creator_id = "creator_review_queue_decline"
    _create_creator(client, decline_creator_id)
    decline = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": decline_creator_id, "body": "No thanks, not interested.", "run_agent": True},
    )
    assert decline.status_code == 200, decline.text

    dnc_creator_id = "creator_review_queue_dnc"
    _create_creator(client, dnc_creator_id)
    dnc = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": dnc_creator_id, "body": "Please unsubscribe me.", "run_agent": True},
    )
    assert dnc.status_code == 200, dnc.text

    queue = client.get("/api/followup-agent/review-queue")
    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 4
    items_by_reply_id = {item["reply"]["id"]: item for item in queue.json()["items"]}
    assert items_by_reply_id[standard.json()["reply"]["id"]]["review_type"] == "standard"
    assert items_by_reply_id[standard.json()["reply"]["id"]]["decision_available"] is True

    failure_item = items_by_reply_id[model_failure.json()["reply"]["id"]]
    assert failure_item["review_type"] == "model_failure"
    assert failure_item["decision_available"] is True
    assert failure_item["run"]["execution_status"] == "failed"
    assert failure_item["run"]["validation_error"]
    assert failure_item["run"]["output"]["raw_output"] == invalid_output

    decline_item = items_by_reply_id[decline.json()["reply"]["id"]]
    assert decline_item["review_type"] == "decline"
    assert decline_item["decision_available"] is False
    dnc_item = items_by_reply_id[dnc.json()["reply"]["id"]]
    assert dnc_item["review_type"] == "dnc_confirmation"
    assert dnc_item["decision_available"] is False

    expected_filter_ids = {
        "standard": standard.json()["reply"]["id"],
        "model_failure": model_failure.json()["reply"]["id"],
        "decline": decline.json()["reply"]["id"],
        "dnc_confirmation": dnc.json()["reply"]["id"],
    }
    for review_type, reply_id in expected_filter_ids.items():
        filtered = client.get(f"/api/followup-agent/review-queue?review_type={review_type}")
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["reply"]["id"] == reply_id

    invalid_filter = client.get("/api/followup-agent/review-queue?review_type=unknown")
    assert invalid_filter.status_code == 422

    approved_failure = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": failure_run["id"],
            "outcome": "approve_draft",
            "final_draft": "A human-authored draft after the model failure.",
            "actor_id": "reviewer_1",
        },
    )
    assert approved_failure.status_code == 201, approved_failure.text


def test_review_item_detail_aggregates_context_and_does_not_write():
    client = TestClient(app)
    creator_id = "creator_review_item_detail"
    _create_creator(
        client,
        creator_id,
        display_name="Detail Creator",
        bio="Detailed creator profile.",
        followers_count=12345,
        owner_bd="bd_detail",
    )
    earlier = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Can you send more details?", "run_agent": False},
    )
    assert earlier.status_code == 200, earlier.text
    current = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert current.status_code == 200, current.text
    first_run = _process_response_run(client, current)
    rerun = client.post("/api/followup-agent/runs", json={"inbound_reply_id": current.json()["reply"]["id"]})
    assert rerun.status_code == 200, rerun.text
    second_run = _process_response_run(client, rerun)

    with SessionLocal() as db:
        db.add(
            models.OutreachEmail(
                id="email_review_item_detail",
                department_code="cross_border",
                creator_id=creator_id,
                subject="Earlier outreach",
                body="Synthetic history for detail aggregation.",
                status="sent",
                sent_at=datetime.utcnow(),
            )
        )
        db.add(
            CreatorOutreachEvent(
                id="event_review_item_detail",
                department_code="cross_border",
                creator_id=creator_id,
                event_type="manual_note",
                note="Synthetic event for detail aggregation.",
                event_at=datetime.utcnow(),
            )
        )
        db.commit()
        before_runs = db.scalar(select(func.count()).select_from(AgentFollowupRun))
        before_decisions = db.scalar(select(func.count()).select_from(HumanReviewDecision))
        reply = db.get(InboundReply, current.json()["reply"]["id"])
        assert reply is not None
        before_status = reply.processing_status

    detail = client.get(f"/api/followup-agent/review-items/{current.json()['reply']['id']}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["item"]["review_type"] == "standard"
    assert payload["item"]["run"]["id"] == second_run["id"]
    assert [run["id"] for run in payload["runs"]] == [first_run["id"], second_run["id"]]
    assert payload["context"]["creator"]["id"] == creator_id
    assert payload["context"]["product"]["product_type"] == "baby care"
    assert payload["context"]["inbound_reply"]["id"] == current.json()["reply"]["id"]
    assert [row["id"] for row in payload["context"]["recent_inbound_replies"]] == [earlier.json()["reply"]["id"]]
    assert payload["context"]["recent_outreach_emails"][0]["id"] == "email_review_item_detail"
    assert payload["context"]["recent_events"][0]["id"] == "event_review_item_detail"
    assert payload["context"]["open_followup_tasks"]
    assert payload["context"]["reference_materials"]

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AgentFollowupRun)) == before_runs
        assert db.scalar(select(func.count()).select_from(HumanReviewDecision)) == before_decisions
        reply = db.get(InboundReply, current.json()["reply"]["id"])
        assert reply is not None
        assert reply.processing_status == before_status


def test_review_item_detail_keeps_terminal_items_read_only_and_rejects_non_pending_replies():
    client = TestClient(app)
    decline_creator_id = "creator_review_item_decline"
    _create_creator(client, decline_creator_id)
    decline = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": decline_creator_id, "body": "No thanks, not interested.", "run_agent": True},
    )
    assert decline.status_code == 200, decline.text

    dnc_creator_id = "creator_review_item_dnc"
    _create_creator(client, dnc_creator_id)
    dnc = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": dnc_creator_id, "body": "Please unsubscribe me.", "run_agent": True},
    )
    assert dnc.status_code == 200, dnc.text

    for response, expected_review_type in ((decline, "decline"), (dnc, "dnc_confirmation")):
        reply_id = response.json()["reply"]["id"]
        detail = client.get(f"/api/followup-agent/review-items/{reply_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["item"]["review_type"] == expected_review_type
        assert detail.json()["item"]["decision_available"] is False
        manual_run = client.post("/api/followup-agent/runs", json={"inbound_reply_id": reply_id})
        assert manual_run.status_code == 409
        assert manual_run.json()["detail"] == "terminal reply cannot run agent"
        terminal_run_id = f"afr_terminal_read_only_{expected_review_type}"
        with SessionLocal() as db:
            terminal_run = AgentFollowupRun(
                id=terminal_run_id,
                department_code="cross_border",
                creator_id=response.json()["reply"]["creator_id"],
                inbound_reply_id=reply_id,
                llm_status="validation_failed",
                execution_status="failed",
                created_at=datetime.utcnow(),
            )
            db.add(terminal_run)
            db.commit()
        terminal_decision = client.post(
            "/api/followup-agent/review-decisions",
            json={
                "agent_followup_run_id": terminal_run_id,
                "outcome": "close_without_draft",
                "actor_id": "reviewer_1",
            },
        )
        assert terminal_decision.status_code == 409
        assert terminal_decision.json()["detail"] == "terminal reply cannot use standard review decision"

    missing = client.get("/api/followup-agent/review-items/missing_reply")
    assert missing.status_code == 404

    standard_creator_id = "creator_review_item_reviewed"
    _create_creator(client, standard_creator_id)
    standard = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": standard_creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert standard.status_code == 200, standard.text
    run = _process_response_run(client, standard)
    reviewed = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "close_without_draft",
            "actor_id": "reviewer_1",
        },
    )
    assert reviewed.status_code == 201, reviewed.text
    non_pending = client.get(f"/api/followup-agent/review-items/{standard.json()['reply']['id']}")
    assert non_pending.status_code == 409
    assert non_pending.json()["detail"] == "reply is not available in the operator workbench"


def test_standard_human_review_can_close_completed_run_without_draft():
    """人工可以关闭无可用草稿的普通回复，但关闭请求不能混入草稿内容。"""

    client = TestClient(app)
    creator_id = "creator_close_human_review"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    run = _process_response_run(client, simulated)

    invalid = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "close_without_draft",
            "final_draft": "This must not be accepted.",
            "actor_id": "reviewer_1",
        },
    )
    assert invalid.status_code == 422

    closed = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "close_without_draft",
            "note": "No follow-up draft is needed.",
            "actor_id": "reviewer_1",
        },
    )
    assert closed.status_code == 201, closed.text
    assert closed.json()["decision"]["final_draft"] is None
    assert closed.json()["reply"]["processing_status"] == "reviewed"


def test_human_review_cannot_use_stale_run_or_requeue_a_reviewed_reply():
    """同一回复只允许最新完成 run 形成一次最终决定，审核后不能重新排队。"""

    client = TestClient(app)
    creator_id = "creator_reviewed_reply_no_requeue"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    reply_id = simulated.json()["reply"]["id"]
    first_run = _process_response_run(client, simulated)

    # 审核前允许人工因资料更新而重跑；此时旧 run 必须不能被当作最终版本审核。
    second_run_response = client.post("/api/followup-agent/runs", json={"inbound_reply_id": reply_id})
    assert second_run_response.status_code == 200, second_run_response.text
    stale_decision = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": first_run["id"],
            "outcome": "approve_draft",
            "final_draft": "This older draft must not be approved.",
            "actor_id": "reviewer_1",
        },
    )
    assert stale_decision.status_code == 409
    assert stale_decision.json()["detail"] == "reply has an active agent followup run"

    with SessionLocal() as db:
        processed = services.process_next_queued_run(db)
        assert processed is not None
        assert processed.id == second_run_response.json()["run"]["id"]
        db.commit()

    # 第二个 run 完成后，旧 run 仍不能被审核；最新 run 可以形成唯一最终决定。
    stale_after_completion = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": first_run["id"],
            "outcome": "close_without_draft",
            "actor_id": "reviewer_1",
        },
    )
    assert stale_after_completion.status_code == 409
    latest_decision = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": second_run_response.json()["run"]["id"],
            "outcome": "approve_draft",
            "final_draft": "This is the only final draft for the reply.",
            "actor_id": "reviewer_1",
        },
    )
    assert latest_decision.status_code == 201, latest_decision.text

    requeue = client.post("/api/followup-agent/runs", json={"inbound_reply_id": reply_id})
    assert requeue.status_code == 409
    assert requeue.json()["detail"] == "reviewed reply cannot run agent"

    duplicate = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["run"] is None
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AgentFollowupRun).where(AgentFollowupRun.inbound_reply_id == reply_id)) == 2
        assert db.scalar(select(func.count()).select_from(HumanReviewDecision).where(HumanReviewDecision.inbound_reply_id == reply_id)) == 1


def test_approved_draft_export_is_audited_and_dnc_blocks_later_export_and_runs():
    """导出只产生快照；DNC 待确认后，系统必须停止后续导出和 Agent 运行。"""

    client = TestClient(app)
    creator_id = "creator_export_and_dnc_block"
    _create_creator(client, creator_id)
    simulated = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert simulated.status_code == 200, simulated.text
    run = _process_response_run(client, simulated)
    approved = client.post(
        "/api/followup-agent/review-decisions",
        json={
            "agent_followup_run_id": run["id"],
            "outcome": "approve_draft",
            "final_draft": "Here are the reviewed campaign details.",
            "actor_id": "reviewer_1",
        },
    )
    assert approved.status_code == 201, approved.text
    decision_id = approved.json()["decision"]["id"]
    approved_reply_id = simulated.json()["reply"]["id"]

    exported = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/exports",
        json={"actor_id": "operator_1"},
    )
    assert exported.status_code == 201, exported.text
    assert exported.json()["export"]["exported_content"] == "Here are the reviewed campaign details."
    assert exported.json()["export"]["delivery_status"] == "not_sent_by_system"

    capability_before_dnc = client.get(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-capability"
    )
    assert capability_before_dnc.status_code == 200, capability_before_dnc.text
    assert capability_before_dnc.json() == {
        "ok": True,
        "delivery_available": False,
        "delivery_status": "not_sent_by_system",
        "delivery_mode": "manual_copy_or_export_only",
        "reason": "external delivery channels are not configured",
    }

    decision = client.get(f"/api/followup-agent/review-decisions/{decision_id}")
    assert decision.status_code == 200, decision.text
    assert len(decision.json()["exports"]) == 1

    dnc_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Please unsubscribe me.", "run_agent": True},
    )
    assert dnc_reply.status_code == 200, dnc_reply.text
    assert dnc_reply.json()["reply"]["processing_status"] == "need_ai_review"

    # A later opt-out takes precedence over an already approved draft for the
    # same creator.  Only the reply that created the confirmation is actionable
    # in the DNC queue; the old reply remains blocked for direct audit reads.
    dnc_queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert dnc_queue.status_code == 200, dnc_queue.text
    assert dnc_queue.json()["total"] == 1
    dnc_queue_item = dnc_queue.json()["items"][0]
    assert dnc_queue_item["reply"]["id"] == dnc_reply.json()["reply"]["id"]
    assert dnc_queue_item["review_type"] == "dnc_confirmation"
    confirmation_id = dnc_queue_item["dnc_confirmation"]["id"]
    assert dnc_queue_item["dnc_confirmation"]["status"] == "pending_confirmation"
    assert approved_reply_id not in {item["reply"]["id"] for item in dnc_queue.json()["items"]}

    reply_ready = client.get("/api/followup-agent/review-queue?review_type=reply_ready")
    assert reply_ready.status_code == 200, reply_ready.text
    assert approved_reply_id not in {item["reply"]["id"] for item in reply_ready.json()["items"]}

    blocked_detail = client.get(f"/api/followup-agent/review-items/{approved_reply_id}")
    assert blocked_detail.status_code == 200, blocked_detail.text
    assert blocked_detail.json()["item"]["review_type"] == "dnc_blocked"
    assert blocked_detail.json()["item"]["decision"] is None
    assert blocked_detail.json()["item"]["run"]["output"] is None
    assert blocked_detail.json()["item"]["dnc_confirmation"] is None
    assert blocked_detail.json()["runs"]
    assert all(run["output"] is None for run in blocked_detail.json()["runs"])

    confirmed_dnc = client.post(
        f"/api/followup-agent/dnc-confirmations/{confirmation_id}/approve",
        json={"actor_id": "reviewer_1"},
    )
    assert confirmed_dnc.status_code == 200, confirmed_dnc.text
    assert confirmed_dnc.json()["confirmation"]["status"] == "confirmed"

    confirmed_queue = client.get("/api/followup-agent/review-queue?review_type=dnc_confirmation")
    assert confirmed_queue.status_code == 200, confirmed_queue.text
    assert confirmed_queue.json()["total"] == 0

    confirmed_detail = client.get(f"/api/followup-agent/review-items/{approved_reply_id}")
    assert confirmed_detail.status_code == 200, confirmed_detail.text
    assert confirmed_detail.json()["item"]["review_type"] == "dnc_blocked"
    assert confirmed_detail.json()["item"]["decision"] is None
    assert confirmed_detail.json()["item"]["dnc_confirmation"] is None
    assert all(run["output"] is None for run in confirmed_detail.json()["runs"])

    blocked_export = client.post(
        f"/api/followup-agent/review-decisions/{decision_id}/exports",
        json={"actor_id": "operator_2"},
    )
    assert blocked_export.status_code == 409
    assert blocked_export.json()["detail"] == "do not contact creator cannot export draft"

    capability_after_dnc = client.get(
        f"/api/followup-agent/review-decisions/{decision_id}/delivery-capability"
    )
    assert capability_after_dnc.status_code == 200, capability_after_dnc.text
    assert capability_after_dnc.json()["delivery_available"] is False
    assert capability_after_dnc.json()["delivery_status"] == "not_sent_by_system"
    assert capability_after_dnc.json()["delivery_mode"] == "blocked_by_do_not_contact"

    later_reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Actually, I am interested.", "run_agent": True},
    )
    assert later_reply.status_code == 200, later_reply.text
    assert later_reply.json()["run"] is None
    assert later_reply.json()["reply"]["processing_status"] == "dnc_blocked"

    blocked_run = client.post(
        "/api/followup-agent/runs",
        json={"inbound_reply_id": later_reply.json()["reply"]["id"]},
    )
    assert blocked_run.status_code == 409
    assert blocked_run.json()["detail"] == "do not contact creator cannot run agent"


def test_running_an_ignored_reply_returns_conflict():
    init_db()
    client = TestClient(app)
    creator_id = "creator_ignored_run"
    _create_creator(client, creator_id)
    reply = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Delivery failed, invalid address.", "run_agent": False},
    )
    assert reply.status_code == 200, reply.text

    response = client.post("/api/followup-agent/runs", json={"inbound_reply_id": reply.json()["reply"]["id"]})
    assert response.status_code == 409
    assert response.json()["detail"] == "ignored reply cannot run agent"


def test_invalid_http_json_returns_422_without_writing_reply():
    client = TestClient(app)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(InboundReply))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        content=b'{"creator_id":',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422

    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(InboundReply))
    assert after == before


def test_invalid_generated_json_is_persisted_and_sent_to_manual_review(monkeypatch):
    client = TestClient(app)
    creator_id = "creator_invalid_generated_json"
    _create_creator(client, creator_id)
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context, prompt: ("not-json", "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    assert run["llm_status"] == "invalid_json"
    assert run["suggested_status"] is None
    assert run["output"]["raw_output"] == "not-json"
    assert run["validation_error"]


def test_pydantic_validation_failure_is_persisted_and_sent_to_manual_review(monkeypatch):
    client = TestClient(app)
    creator_id = "creator_invalid_suggestion"
    _create_creator(client, creator_id)
    invalid_output = json.dumps({"reply_category": "interested", "confidence": 0.9})
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context, prompt: (invalid_output, "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    assert run["llm_status"] == "validation_failed"
    assert run["suggested_status"] is None
    assert run["output"]["raw_output"] == invalid_output
    assert run["validation_error"]


def test_low_suggestion_confidence_requires_manual_review(monkeypatch):
    client = TestClient(app)
    creator_id = "creator_low_suggestion_confidence"
    _create_creator(client, creator_id)
    low_confidence_output = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks for your interest.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.69,
            "warnings": [],
            "reasoning_summary": "The creator expressed interest.",
        }
    )
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context, prompt: (low_confidence_output, "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"]["processing_status"] == "need_ai_review"


def test_agent_suggestion_exposes_explicit_human_review_decision():
    """模型输出应能明确声明人工复核结论，避免只依赖置信度推断。"""

    suggestion = AgentSuggestion.model_validate(
        {
            "reply_category": "negotiation",
            "suggested_reply": "I will confirm the terms before we proceed.",
            "next_action": "clarify_terms",
            "suggested_status": "pending_followup",
            "confidence": 0.9,
            "warnings": [],
            "reasoning_summary": "The creator is discussing collaboration terms.",
            "requires_human_review": True,
            "review_reasons": ["negotiation_requires_manual_review"],
        }
    )

    assert suggestion.model_dump().get("requires_human_review") is True
    assert suggestion.model_dump().get("review_reasons") == ["negotiation_requires_manual_review"]


def test_agent_suggestion_rejects_unknown_next_action():
    """真实模型不能生成系统无法路由的后续动作。"""

    with pytest.raises(ValidationError, match="next_action"):
        AgentSuggestion.model_validate(
            {
                "reply_category": "interested",
                "suggested_reply": "Thanks for your interest.",
                "next_action": "unknown_future_action",
                "suggested_status": "pending_followup",
                "confidence": 0.9,
                "reasoning_summary": "The creator expressed interest.",
            }
        )


def test_prompt_package_includes_pydantic_next_action_contract():
    """模型提示词应携带与本地校验一致的 JSON Schema 动作约束。"""

    prompts = importlib.import_module("app.prompts")
    package = prompts.build_prompt_package(
        {
            "reply_category": "interested",
            "creator": {},
            "inbound_reply": {"body": "Sounds interesting."},
        }
    )

    assert '"next_action"' in package.system_prompt
    for action in (
        "send_campaign_details",
        "clarify_terms",
        "acknowledge_and_close",
        "ask_clarifying_question",
        "verify_contact_method",
    ):
        assert f'"{action}"' in package.system_prompt


def test_agent_suggestion_json_schema_exposes_category_and_status_enums():
    """Provider 看到的 Schema 必须直接声明分类和状态白名单。"""

    schema = AgentSuggestion.model_json_schema()
    properties = schema["properties"]

    assert properties["reply_category"]["enum"] == [
        "interested",
        "need_more_info",
        "negotiation",
        "not_interested",
        "bounce_or_invalid",
        "unclear",
    ]
    assert properties["suggested_status"]["enum"] == [
        "pending_followup",
        "pending_reply",
        "communicating",
        "dropped",
    ]


def test_v2_prompt_makes_rule_category_and_route_mapping_explicit():
    """v2 应把规则层结果和允许路由放在模型可见的高优先级指令中。"""

    prompts = importlib.import_module("app.prompts")
    package = prompts.build_prompt_package(
        {
            "reply_category": "negotiation",
            "creator": {},
            "product": None,
            "inbound_reply": {"subject": "Terms", "body": "Can we discuss the budget?"},
        },
        prompt_version="reply_followup_v2",
    )

    assert package.prompt_version == "reply_followup_v2"
    assert "Authoritative rule category: negotiation" in package.system_prompt
    assert "negotiation -> clarify_terms / pending_followup / requires_human_review=true" in package.system_prompt
    assert "requires_human_review must always be true" in package.system_prompt
    assert "Never set requires_human_review to false." in package.system_prompt
    assert "Campaign detail policy" in package.system_prompt
    assert "Do not invent any other value." in package.system_prompt


def test_prompt_package_default_uses_validated_v2():
    """业务默认使用已通过回归评测的 V2 提示词。"""

    prompts = importlib.import_module("app.prompts")
    package = prompts.build_prompt_package(
        {"creator": {}, "product": None, "inbound_reply": {"subject": "Hi", "body": "Interested"}}
    )

    assert package.prompt_version == "reply_followup_v2"


def test_unknown_model_next_action_is_persisted_as_validation_failure(monkeypatch):
    """Provider 即使返回合法 JSON，未知动作也应落入人工复核失败路径。"""

    client = TestClient(app)
    creator_id = "creator_unknown_next_action"
    _create_creator(client, creator_id)
    unknown_action_output = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks for your interest.",
            "next_action": "unknown_future_action",
            "suggested_status": "pending_followup",
            "confidence": 0.9,
            "reasoning_summary": "The creator expressed interest.",
        }
    )
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context, prompt: (unknown_action_output, "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    assert run["llm_status"] == "validation_failed"
    assert run["suggested_status"] is None
    assert run["validation_error"]


def test_configured_siliconflow_provider_output_is_used(monkeypatch):
    """配置 Provider Key 后，应使用结构化模型输出而非本地 fallback。"""

    client = TestClient(app)
    creator_id = "creator_siliconflow_success"
    _create_creator(client, creator_id)
    provider_output = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks for your interest. I will share the details.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.91,
            "reasoning_summary": "The creator expressed clear interest.",
            "requires_human_review": False,
            "review_reasons": [],
        }
    )
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    monkeypatch.setattr(
        services,
        "call_siliconflow_json",
        lambda system_prompt, user_prompt: provider_output,
        raising=False,
    )

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    run = _process_response_run(client, response)
    assert run["llm_status"] == "success"
    assert run["output"]["confidence"] == 0.91


def test_siliconflow_provider_error_is_persisted_for_manual_review(monkeypatch):
    """Provider 调用异常不可静默回退，必须留下失败 run 供人工处理。"""

    client = TestClient(app)
    creator_id = "creator_siliconflow_error"
    _create_creator(client, creator_id)
    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")

    def raise_provider_error(system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("provider request failed")

    monkeypatch.setattr(services, "call_siliconflow_json", raise_provider_error, raising=False)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    assert run["llm_status"] == "provider_error"
    assert run["validation_error"] == "provider request failed"


def test_siliconflow_client_defaults_to_v32_with_thinking_disabled(monkeypatch):
    """默认模型为 V3.2，关闭 thinking 且不传 V4 Flash 专属参数。"""

    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    monkeypatch.delenv("SILICONFLOW_MODEL", raising=False)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    llm = importlib.import_module("app.llm")

    assert llm.call_siliconflow_json("system contract", "user context") == '{"ok": true}'
    assert captured["client"] == {
        "api_key": "test-key",
        "base_url": "https://api.siliconflow.cn/v1",
            "timeout": 90.0,
        "max_retries": 0,
    }
    assert captured["request"] == {
        "model": "deepseek-ai/DeepSeek-V3.2",
        "messages": [
            {"role": "system", "content": "system contract"},
            {"role": "user", "content": "user context"},
        ],
        "response_format": {"type": "json_object"},
        "extra_body": {"enable_thinking": False},
        "temperature": 0.2,
        "max_tokens": 512,
    }


def test_siliconflow_v32_disables_thinking_without_v4_reasoning_parameter(monkeypatch):
    """V3.2 应使用关闭思考参数，不能沿用只属于 V4 Flash 的强度参数。"""

    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    monkeypatch.setenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3.2")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    llm = importlib.import_module("app.llm")

    assert llm.call_siliconflow_json("system contract", "user context") == '{"ok": true}'
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["model"] == "deepseek-ai/DeepSeek-V3.2"
    assert request["extra_body"] == {"enable_thinking": False}
    assert "reasoning_effort" not in request


def test_siliconflow_v4_flash_keeps_its_reasoning_parameter(monkeypatch):
    """V4 Flash 仅在被显式选择时使用 reasoning_effort=high。"""

    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs: object) -> SimpleNamespace:
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("SILICONFLOW_API_KEY", "test-key")
    monkeypatch.setenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    llm = importlib.import_module("app.llm")

    assert llm.call_siliconflow_json("system contract", "user context") == '{"ok": true}'
    request = captured["request"]
    assert isinstance(request, dict)
    assert request["reasoning_effort"] == "high"
    assert "extra_body" not in request


def test_env_example_documents_siliconflow_configuration():
    """仓库应提供无密钥的环境变量模板，避免把真实 Key 写进源码。"""

    example_path = Path(__file__).resolve().parents[1] / ".env.example"
    assert example_path.is_file()
    content = example_path.read_text(encoding="utf-8")
    assert "SILICONFLOW_API_KEY=" in content
    assert "SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2" in content


def test_evaluation_suite_is_synthetic_and_has_the_planned_pilot_size():
    """评测样本应为可复现的脱敏合成数据，且开发集固定为 24 条。"""

    evaluation = importlib.import_module("app.evaluation")
    cases = evaluation.load_suite("pilot")

    assert len(cases) == 24
    assert all(case["id"].startswith("pilot_") for case in cases)
    assert all("@" not in json.dumps(case, ensure_ascii=False) for case in cases)
    assert all(case["context"]["product"]["campaign_timeline"] for case in cases)
    assert all(case["context"]["product"]["campaign_deliverables"] for case in cases)
    assert all(case["context"]["product"]["budget_guidance"] for case in cases)


def test_evaluation_summary_tracks_validation_routing_review_and_latency():
    """评测汇总必须区分解析、校验、路由、人工复核与延迟。"""

    evaluation = importlib.import_module("app.evaluation")
    summary = evaluation.summarize_records(
        [
            {
                "outcome": "success",
                "json_parse_valid": True,
                "pydantic_valid": True,
                "route_exact": True,
                "manual_review_expected": False,
                "manual_review_actual": False,
                "latency_ms": 100.0,
            },
            {
                "outcome": "validation_failed",
                "json_parse_valid": True,
                "pydantic_valid": False,
                "route_exact": False,
                "manual_review_expected": True,
                "manual_review_actual": False,
                "latency_ms": 200.0,
            },
        ]
    )

    assert summary["total"] == 2
    assert summary["json_parse_rate"] == 1.0
    assert summary["pydantic_pass_rate"] == 0.5
    assert summary["route_exact_rate"] == 0.5
    assert summary["missed_manual_review_count"] == 1
    assert summary["p95_latency_ms"] == 200.0


def test_evaluation_requires_explicit_live_flag(monkeypatch):
    """默认评测不能因读取 .env 而意外消耗真实模型额度。"""

    evaluation = importlib.import_module("app.evaluation")
    monkeypatch.setattr(
        evaluation,
        "call_siliconflow_json",
        lambda system_prompt, user_prompt: pytest.fail("Provider must not be called without --live"),
    )

    with pytest.raises(ValueError, match="--live"):
        evaluation.run_suite("pilot", live=False)


def test_context_preflight_suite_runs_without_provider_and_counts_missing_briefs(monkeypatch):
    """资料缺失评测是本地预检，不应要求 Key 或调用真实模型。"""

    evaluation = importlib.import_module("app.evaluation")
    monkeypatch.setattr(
        evaluation,
        "call_siliconflow_json",
        lambda system_prompt, user_prompt: pytest.fail("Context preflight must not call the provider"),
    )

    records, summary = evaluation.run_suite("context_preflight", live=False)

    assert len(records) == 6
    assert all(record["outcome"] == "context_insufficient" for record in records)
    assert summary["context_insufficient_count"] == 6
    assert summary["provider_attempt_count"] == 0
    assert summary["preflight_route_exact_rate"] == 1.0
    assert summary["pydantic_pass_rate"] is None


def test_evaluation_can_run_a_named_prompt_version_without_real_provider(monkeypatch):
    """评测器应明确把候选提示词版本传入每条样本，而不是修改生产默认值。"""

    evaluation = importlib.import_module("app.evaluation")
    prompts = importlib.import_module("app.prompts")
    observed_versions: list[str] = []
    original_builder = prompts.build_prompt_package

    def capture_builder(context, *, prompt_version):
        observed_versions.append(prompt_version)
        return original_builder(context, prompt_version=prompt_version)

    valid_output = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "I will send the details.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.9,
            "reasoning_summary": "Synthetic evaluation response.",
            "requires_human_review": False,
            "review_reasons": [],
        }
    )
    monkeypatch.setattr(evaluation, "build_prompt_package", capture_builder)
    monkeypatch.setattr(evaluation, "call_siliconflow_json", lambda system_prompt, user_prompt: valid_output)

    records, _ = evaluation.run_suite("pilot", live=True, prompt_version="reply_followup_v2")

    assert len(records) == 24
    assert observed_versions == ["reply_followup_v2"] * 24


def test_evaluation_defaults_to_v2_for_regression(monkeypatch):
    """回归评测未指定版本时应覆盖生产默认 V2。"""

    evaluation = importlib.import_module("app.evaluation")
    prompts = importlib.import_module("app.prompts")
    observed_versions: list[str] = []
    current_category: str | None = None
    original_builder = prompts.build_prompt_package
    expected_routes = {
        "interested": ("send_campaign_details", "pending_followup"),
        "need_more_info": ("send_campaign_details", "pending_followup"),
        "negotiation": ("clarify_terms", "pending_followup"),
        "not_interested": ("acknowledge_and_close", "dropped"),
        "bounce_or_invalid": ("verify_contact_method", "pending_followup"),
        "unclear": ("ask_clarifying_question", "pending_followup"),
    }

    def capture_builder(context, *, prompt_version):
        nonlocal current_category
        observed_versions.append(prompt_version)
        current_category = context["reply_category"]
        return original_builder(context, prompt_version=prompt_version)

    def valid_output(system_prompt, user_prompt):
        assert current_category is not None
        next_action, suggested_status = expected_routes[current_category]
        return json.dumps(
            {
                "reply_category": current_category,
                "suggested_reply": "Synthetic draft for human review.",
                "next_action": next_action,
                "suggested_status": suggested_status,
                "confidence": 0.9,
                "reasoning_summary": "Synthetic evaluation response.",
                "requires_human_review": True,
                "review_reasons": ["Human approval is required before any response is sent."],
            }
        )

    monkeypatch.setattr(evaluation, "build_prompt_package", capture_builder)
    monkeypatch.setattr(evaluation, "call_siliconflow_json", valid_output)

    records, summary = evaluation.run_suite("pilot", live=True)

    assert len(records) == 24
    assert observed_versions == ["reply_followup_v2"] * 24
    assert summary["prompt_version"] == "reply_followup_v2"
    assert summary["pydantic_pass_rate"] == 1.0
    assert summary["route_exact_rate"] == 1.0
    assert summary["missed_manual_review_count"] == 0
    assert all(record["outcome"] == "success" for record in records)


def test_explicit_human_review_output_moves_reply_to_manual_review(monkeypatch):
    """即使置信度和上下文均正常，模型明确要求复核时也必须转人工。"""

    client = TestClient(app)
    creator_id = "creator_explicit_review"
    _create_creator(client, creator_id)
    reviewed_output = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks for your interest. I will send the campaign details.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.9,
            "warnings": [],
            "reasoning_summary": "The creator expressed interest but asked for a manual check.",
            "requires_human_review": True,
            "review_reasons": ["sensitive_collaboration_detail"],
        }
    )
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda *args: (reviewed_output, "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    run = _process_response_run(client, response)
    assert run["output"]["requires_human_review"] is True
    assert "sensitive_collaboration_detail" in run["output"]["warnings"]


def test_missing_creator_context_adds_warning_and_requires_manual_review():
    client = TestClient(app)
    creator_id = "creator_missing_context"
    _create_creator(client, creator_id, recommendation_reason=None, recommended_product_type="baby care")

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert "missing_creator_context" in _process_response_run(client, response)["output"]["warnings"]


def test_missing_product_context_adds_warning_and_requires_manual_review():
    client = TestClient(app)
    creator_id = "creator_missing_product"
    _create_creator(client, creator_id, recommendation_reason="Strong audience match.", recommended_product_type=None)

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert "missing_product_context" in _process_response_run(client, response)["output"]["warnings"]


def test_simulate_reply_queues_run_without_calling_generator(monkeypatch):
    """入站接口只创建待执行任务，不能等待或直接调用模型生成。"""

    client = TestClient(app)
    creator_id = "creator_async_queue"
    _create_creator(client, creator_id)
    monkeypatch.setattr(
        services,
        "generate_raw_followup_output",
        lambda *_: pytest.fail("simulate reply must not invoke the generator"),
    )

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert payload["run"]["execution_status"] == "queued"
    assert payload["run"]["llm_status"] == "pending"
    assert payload["run"]["output"] is None


def test_worker_processes_queued_run_and_records_completion(monkeypatch):
    """worker 领取任务后才生成建议，并回写同一条 run 的执行结果。"""

    monkeypatch.delenv("SILICONFLOW_MODEL", raising=False)
    client = TestClient(app)
    creator_id = "creator_async_worker"
    _create_creator(client, creator_id)
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert queued.status_code == 200, queued.text
    run_id = queued.json()["run"]["id"]
    generated = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks, I will share the campaign details for your review.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.91,
            "reasoning_summary": "The creator expressed clear collaboration interest.",
        }
    )
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda *_: (generated, "success"))

    with SessionLocal() as db:
        processed = services.process_next_queued_run(db)
        assert processed is not None
        assert processed.id == run_id
        db.commit()

    completed = client.get(f"/api/followup-agent/runs/{run_id}")
    assert completed.status_code == 200, completed.text
    run = completed.json()["run"]
    assert run["execution_status"] == "succeeded"
    assert run["llm_status"] == "success"
    assert run["provider_model"] == "deepseek-ai/DeepSeek-V3.2"
    assert run["output"]["next_action"] == "send_campaign_details"
    assert run["started_at"] is not None
    assert run["finished_at"] is not None


def test_worker_process_once_returns_processed_run_id(monkeypatch):
    """独立 worker 的单次模式应处理一条任务并返回其 run ID。"""

    import app.worker as worker

    client = TestClient(app)
    creator_id = "creator_worker_command"
    _create_creator(client, creator_id)
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert queued.status_code == 200, queued.text
    generated = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks, I will send the campaign details.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.91,
            "reasoning_summary": "The creator is interested.",
        }
    )
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda *_: (generated, "success"))

    assert worker.process_once() == queued.json()["run"]["id"]


def test_worker_commits_running_claim_before_blocking_provider_call(monkeypatch):
    """Worker 调用 Provider 前必须让其他会话可见 running 租约。"""

    import app.worker as worker

    client = TestClient(app)
    _create_creator(client, "creator_committed_claim")
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_committed_claim", "body": "Sounds interesting.", "run_agent": True},
    )
    run_id = queued.json()["run"]["id"]
    provider_started = threading.Event()
    release_provider = threading.Event()
    generated = json.dumps(
        {
            "reply_category": "interested",
            "suggested_reply": "Thanks, I will share the campaign details.",
            "next_action": "send_campaign_details",
            "suggested_status": "pending_followup",
            "confidence": 0.91,
            "reasoning_summary": "The creator is interested.",
        }
    )

    def block_provider(*_: object) -> tuple[str, str]:
        provider_started.set()
        assert release_provider.wait(timeout=3)
        return generated, "success"

    monkeypatch.setattr(services, "generate_raw_followup_output", block_provider)
    thread = threading.Thread(target=worker.process_once)
    thread.start()
    assert provider_started.wait(timeout=3)
    try:
        with SessionLocal() as db:
            claimed = db.get(AgentFollowupRun, run_id)
            assert claimed is not None
            assert claimed.execution_status == "running"
            assert claimed.claim_token
            assert claimed.lease_expires_at is not None
        write_response = client.post(
            "/api/followup-agent/creators",
            json={"id": "creator_write_during_provider", "handle": "write_during_provider"},
        )
        assert write_response.status_code == 201, write_response.text
    finally:
        release_provider.set()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_expired_running_run_is_failed_without_automatic_retry():
    """过期租约必须转人工处理，不能回到 queued 或再次调用模型。"""

    client = TestClient(app)
    _create_creator(client, "creator_expired_lease")
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_expired_lease", "body": "Sounds interesting.", "run_agent": True},
    )
    run_id = queued.json()["run"]["id"]
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, run_id)
        assert run is not None
        run.execution_status = "running"
        run.claim_token = "lost-worker-claim"
        run.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    with SessionLocal() as db:
        assert services.recover_expired_runs(db) == 1
        db.commit()

    completed = client.get(f"/api/followup-agent/runs/{run_id}")
    assert completed.status_code == 200
    run = completed.json()["run"]
    assert run["execution_status"] == "failed"
    assert run["llm_status"] == "worker_lost"
    assert run["validation_error"] == "worker lease expired before completion"
    assert run["lease_expires_at"] is None


def test_stale_worker_claim_cannot_overwrite_current_run_state():
    """旧 Worker 的 claim_token 失效后不得再处理或覆盖该 run。"""

    client = TestClient(app)
    _create_creator(client, "creator_stale_claim")
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_stale_claim", "body": "Sounds interesting.", "run_agent": True},
    )
    run_id = queued.json()["run"]["id"]
    with SessionLocal() as db:
        claimed = services.claim_next_queued_run(db)
        assert claimed is not None
        db.commit()
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, run_id)
        assert run is not None
        run.claim_token = "newer-worker-claim"
        db.commit()

    assert services.process_claimed_run(claimed) is None
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, run_id)
        assert run is not None
        assert run.execution_status == "running"
        assert run.claim_token == "newer-worker-claim"


def test_worker_persists_unexpected_context_error_without_waiting_for_lease(monkeypatch):
    """上下文拼装意外失败时应立即留痕，不能等租约过期才变为 worker_lost。"""

    import app.worker as worker

    client = TestClient(app)
    _create_creator(client, "creator_unexpected_worker_error")
    queued = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": "creator_unexpected_worker_error", "body": "Sounds interesting.", "run_agent": True},
    )
    run_id = queued.json()["run"]["id"]

    def raise_context_error(*_: object) -> dict[str, object]:
        raise RuntimeError("context assembly failed")

    monkeypatch.setattr(services, "build_followup_context", raise_context_error)

    assert worker.process_once() == run_id
    completed = client.get(f"/api/followup-agent/runs/{run_id}")
    assert completed.status_code == 200
    run = completed.json()["run"]
    assert run["execution_status"] == "failed"
    assert run["llm_status"] == "worker_unexpected_error"
    assert run["validation_error"] == "RuntimeError: context assembly failed"
    assert run["lease_expires_at"] is None
    assert client.get(f"/api/followup-agent/replies/{queued.json()['reply']['id']}").json()["reply"]["processing_status"] == "need_ai_review"


def test_reference_material_versions_are_used_in_prompt_context_and_run_snapshot():
    client = TestClient(app)
    created = client.post(
        "/api/followup-agent/reference-materials",
        json={"reference_key": "company-policy", "scope": "company_policy", "material_type": "company_policy", "title": "General policy", "content": "Do not promise exclusivity."},
    )
    updated = client.patch(
        "/api/followup-agent/reference-materials/company-policy",
        json={"scope": "company_policy", "material_type": "company_policy", "title": "General policy", "content": "Do not promise exclusivity or guaranteed sales."},
    )
    campaign = client.post(
        "/api/followup-agent/reference-materials",
        json={"reference_key": "baby-care-brief", "scope": "campaign", "material_type": "campaign_details", "product_type": "baby care", "title": "Baby campaign", "content": "One short video and one product link."},
    )
    assert created.status_code == 201, created.text
    assert updated.status_code == 200, updated.text
    assert campaign.status_code == 201, campaign.text
    assert created.json()["reference_material"]["version"] == 1
    assert updated.json()["reference_material"]["version"] == 2

    _create_creator(client, "creator_reference_snapshot")
    reply = client.post("/api/followup-agent/simulate-reply", json={"creator_id": "creator_reference_snapshot", "body": "Sounds interesting.", "run_agent": True})
    assert reply.status_code == 200, reply.text
    run = _process_response_run(client, reply)
    versions = {(row["reference_key"], row["version"]) for row in run["reference_materials"]}
    assert ("company-policy", 2) in versions
    assert ("baby-care-brief", 1) in versions
    assert "guaranteed sales" in run["rendered_prompt"]


def test_automatic_generation_skips_terminal_unclear_and_incomplete_replies():
    """低价值或资料不足回复不能自动消耗模型额度，但人工可以手动请求建议。"""

    client = TestClient(app)
    creator_id = "creator_generation_gate"
    _create_creator(client, creator_id)

    declined = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "No thanks, not interested.", "run_agent": True},
    )
    unclear = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Thanks.", "run_agent": True},
    )
    incomplete = client.post(
        "/api/followup-agent/simulate-reply",
        json={
            "creator_id": creator_id,
            "body": "Could you send the campaign timeline, deliverables, and budget?",
            "run_agent": True,
        },
    )

    assert declined.status_code == 200, declined.text
    assert unclear.status_code == 200, unclear.text
    assert incomplete.status_code == 200, incomplete.text
    assert declined.json()["run"] is None
    assert unclear.json()["run"] is None
    assert incomplete.json()["run"] is None
    assert unclear.json()["reply"]["processing_status"] == "need_ai_review"
    assert incomplete.json()["reply"]["processing_status"] == "need_ai_review"

    manual = client.post(
        "/api/followup-agent/runs",
        json={"inbound_reply_id": unclear.json()["reply"]["id"]},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["run"]["execution_status"] == "queued"
    with SessionLocal() as db:
        run = db.get(AgentFollowupRun, manual.json()["run"]["id"])
        assert run is not None
        assert run.created_by == "manual"


def _process_response_run(client: TestClient, response: object) -> dict[str, object]:
    """让结果断言显式经过 worker；未自动入队时模拟人工主动请求。"""

    payload = response.json()
    run = payload["run"]
    if run is None:
        manual = client.post("/api/followup-agent/runs", json={"inbound_reply_id": payload["reply"]["id"]})
        assert manual.status_code == 200, manual.text
        run = manual.json()["run"]
    with SessionLocal() as db:
        processed = services.process_next_queued_run(db)
        assert processed is not None
        assert processed.id == run["id"]
        db.commit()
    completed = client.get(f"/api/followup-agent/runs/{run['id']}")
    assert completed.status_code == 200, completed.text
    return completed.json()["run"]


def test_demo_seed_is_idempotent_and_populates_all_operator_workbench_states(monkeypatch):
    """演示种子只写入固定本地样例，不能调用模型或创建外发指令。"""

    monkeypatch.setattr(
        services,
        "generate_raw_followup_output",
        lambda *_args, **_kwargs: pytest.fail("demo seed must not call the LLM generator"),
    )

    with SessionLocal() as db:
        created = seed_demo_data(db)
        db.commit()
    assert created > 0

    client = TestClient(app)
    queue = client.get("/api/followup-agent/review-queue")
    assert queue.status_code == 200, queue.text
    assert {item["review_type"] for item in queue.json()["items"]} == {
        "standard",
        "model_failure",
        "generation_pending",
        "decline",
        "dnc_confirmation",
        "approved_draft",
    }

    standard_detail = client.get("/api/followup-agent/review-items/demo_reply_standard")
    assert standard_detail.status_code == 200, standard_detail.text
    context = standard_detail.json()["context"]
    assert context["product"]["product_type"] == "demo_audio_accessory"
    assert context["reference_materials"]
    assert context["recent_inbound_replies"]
    assert context["recent_outreach_emails"]
    assert context["recent_events"]
    assert context["open_followup_tasks"]
    AgentSuggestion.model_validate(standard_detail.json()["item"]["run"]["output"])

    failure = client.get("/api/followup-agent/review-items/demo_reply_failure")
    assert failure.status_code == 200, failure.text
    assert failure.json()["item"]["run"]["llm_status"] == "validation_failed"
    assert failure.json()["item"]["run"]["validation_error"] == "suggested_reply and confidence are required"

    with SessionLocal() as db:
        counts_before = {
            "creators": db.scalar(select(func.count()).select_from(Creator)),
            "replies": db.scalar(select(func.count()).select_from(InboundReply)),
            "runs": db.scalar(select(func.count()).select_from(AgentFollowupRun)),
            "decisions": db.scalar(select(func.count()).select_from(HumanReviewDecision)),
        }
        assert db.scalar(select(func.count()).select_from(models.SimulatedOutboundInstruction)) == 0
        second_created = seed_demo_data(db)
        db.commit()
        counts_after = {
            "creators": db.scalar(select(func.count()).select_from(Creator)),
            "replies": db.scalar(select(func.count()).select_from(InboundReply)),
            "runs": db.scalar(select(func.count()).select_from(AgentFollowupRun)),
            "decisions": db.scalar(select(func.count()).select_from(HumanReviewDecision)),
        }
        assert db.scalar(select(func.count()).select_from(models.SimulatedOutboundInstruction)) == 0

    assert second_created == 0
    assert counts_after == counts_before


def _create_creator(
    client: TestClient,
    creator_id: str,
    recommendation_reason: str | None = "Audience matches the campaign.",
    recommended_product_type: str | None = "baby care",
    **overrides: object,
) -> None:
    payload = {
        "id": creator_id,
        "handle": creator_id,
        "email": f"{creator_id}@example.com",
        "recommendation_reason": recommendation_reason,
        "recommended_product_type": recommended_product_type,
    }
    payload.update(overrides)
    response = client.post(
        "/api/followup-agent/creators",
        json=payload,
    )
    assert response.status_code == 201, response.text


def _creator_replace_payload(**overrides: object) -> dict[str, object | None]:
    payload: dict[str, object | None] = {
        "department_code": "cross_border",
        "platform": "tiktok",
        "handle": "replacement_handle",
        "display_name": "Replacement Name",
        "profile_url": "https://example.com/replacement",
        "bio": "Replacement bio",
        "email": "replacement@example.com",
        "followers_count": 1000,
        "owner_bd": "bd_1",
        "recommendation_reason": "Replacement reason.",
        "recommended_product_type": "baby care",
        "recommended_collab_type": "affiliate",
    }
    payload.update(overrides)
    return payload


def _product_payload(**overrides: object) -> dict[str, object | None]:
    payload: dict[str, object | None] = {
        "id": "product_default",
        "product_type": "default type",
        "name": "Default Product",
        "summary": "Default product summary.",
        "selling_points": ["point one", "point two"],
        "target_audience": "Default audience",
        "collaboration_requirements": "One short video.",
        "forbidden_claims": ["No medical claims"],
        "notes": "Default notes.",
        "is_active": True,
    }
    payload.update(overrides)
    return payload
