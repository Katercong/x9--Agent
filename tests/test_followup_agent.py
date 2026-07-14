from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
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
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    AgentFollowupRun,
    Creator,
    CreatorOutreachEvent,
    FollowupTask,
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
    assert payload["run"]["reply_category"] == "need_more_info"
    assert payload["run"]["llm_status"] == "context_insufficient"
    assert payload["run"]["output"]["next_action"] == "prepare_campaign_brief"
    assert payload["reply"]["processing_status"] == "need_ai_review"
    assert payload["run"]["output"]["requires_human_review"] is True
    assert "human_approval_required" in payload["run"]["output"]["warnings"]
    assert payload["reply"]["reply_category"] == "need_more_info"
    assert payload["reply"]["classification_confidence"] == 0.82
    assert payload["reply"]["classification_reason"].startswith("matched_keyword:")
    assert payload["reply"]["classified_at"] is not None

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


def test_not_interested_drops_creator_and_cancels_existing_reply_followup_task():
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
    assert rejection.json()["run"]["suggested_status"] == "dropped"

    with SessionLocal() as db:
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status == "dropped"
        assert creator.do_not_contact_status == "none"
        tasks = list(db.scalars(select(FollowupTask).where(FollowupTask.creator_id == creator_id)).all())
        assert len(tasks) == 1
        assert tasks[0].status == "cancelled"
        assert "declined" in (tasks[0].reason or "")
        event_types = list(
            db.scalars(
                select(CreatorOutreachEvent.event_type).where(CreatorOutreachEvent.creator_id == creator_id)
            ).all()
        )
        assert event_types.count("creator_declined") == 1


def test_dropped_creator_reengagement_requires_human_confirmation_before_status_restore():
    """拒绝后的重新表达意向只能进入确认队列，不能自动恢复达人业务状态。"""

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
        assert creator.current_status == "dropped"
        task = db.scalar(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator_id)
            .where(FollowupTask.task_type == "reengagement_review")
        )
        assert task is not None
        assert task.status == "open"


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
    output = response.json()["run"]["output"]
    assert response.json()["reply"]["processing_status"] == "need_ai_review"
    assert response.json()["run"]["llm_status"] == "context_insufficient"
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
        assert creator.current_status == "dropped"
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
    context = current.json()["run"]["context"]
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
    assert "missing_product_context" in missing_response.json()["run"]["output"]["warnings"]

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
    assert "missing_product_context" in inactive_response.json()["run"]["output"]["warnings"]


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
    assert package.prompt_version == "reply_followup_v1"
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
    run = response.json()["run"]
    assert run["prompt_version"] == "reply_followup_v1"
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
    assert first.json()["reply"]["external_message_id"] is None

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
    assert payload["run"]["llm_status"] == "invalid_json"
    assert payload["run"]["suggested_status"] is None
    assert payload["run"]["output"]["raw_output"] == "not-json"
    assert payload["run"]["validation_error"]


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
    assert payload["run"]["llm_status"] == "validation_failed"
    assert payload["run"]["suggested_status"] is None
    assert payload["run"]["output"]["raw_output"] == invalid_output
    assert payload["run"]["validation_error"]


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
    assert "Campaign detail policy" in package.system_prompt
    assert "Do not invent any other value." in package.system_prompt


def test_prompt_package_default_remains_v1_during_evaluation():
    """正式评测通过前，普通业务调用不能被隐式切换到 v2。"""

    prompts = importlib.import_module("app.prompts")
    package = prompts.build_prompt_package(
        {"creator": {}, "product": None, "inbound_reply": {"subject": "Hi", "body": "Interested"}}
    )

    assert package.prompt_version == "reply_followup_v1"


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
    assert payload["run"]["llm_status"] == "validation_failed"
    assert payload["run"]["suggested_status"] is None
    assert payload["run"]["validation_error"]


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
    payload = response.json()
    assert payload["run"]["llm_status"] == "success"
    assert payload["run"]["output"]["confidence"] == 0.91


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
    assert payload["run"]["llm_status"] == "provider_error"
    assert payload["run"]["validation_error"] == "provider request failed"


def test_siliconflow_client_uses_openai_json_mode(monkeypatch):
    """硅基流动调用参数应固定为 OpenAI 兼容 JSON Mode。"""

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
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    llm = importlib.import_module("app.llm")

    assert llm.call_siliconflow_json("system contract", "user context") == '{"ok": true}'
    assert captured["client"] == {
        "api_key": "test-key",
        "base_url": "https://api.siliconflow.cn/v1",
        "timeout": 20.0,
        "max_retries": 0,
    }
    assert captured["request"] == {
        "model": "deepseek-ai/DeepSeek-V4-Flash",
        "messages": [
            {"role": "system", "content": "system contract"},
            {"role": "user", "content": "user context"},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 512,
    }


def test_env_example_documents_siliconflow_configuration():
    """仓库应提供无密钥的环境变量模板，避免把真实 Key 写进源码。"""

    example_path = Path(__file__).resolve().parents[1] / ".env.example"
    assert example_path.is_file()
    content = example_path.read_text(encoding="utf-8")
    assert "SILICONFLOW_API_KEY=" in content
    assert "SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V4-Flash" in content


def test_evaluation_suite_is_synthetic_and_has_the_planned_pilot_size():
    """评测样本应为可复现的脱敏合成数据，且开发集固定为 24 条。"""

    evaluation = importlib.import_module("app.evaluation")
    cases = evaluation.load_suite("pilot")

    assert len(cases) == 24
    assert all(case["id"].startswith("pilot_") for case in cases)
    assert all("@" not in json.dumps(case, ensure_ascii=False) for case in cases)


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
    assert payload["run"]["output"]["requires_human_review"] is True
    assert "sensitive_collaboration_detail" in payload["run"]["output"]["warnings"]


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
    assert "missing_creator_context" in payload["run"]["output"]["warnings"]


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
    assert "missing_product_context" in payload["run"]["output"]["warnings"]


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
