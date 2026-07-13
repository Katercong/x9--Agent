from __future__ import annotations

import os
import tempfile
from datetime import datetime
import json

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False, suffix='.db').name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AgentFollowupRun, Creator, CreatorOutreachEvent, FollowupTask, InboundReply  # noqa: E402
from app import services  # noqa: E402
from app.services import classify_reply  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database():
    """每个用例使用干净表结构，避免上一条回复影响本用例的状态和计数。"""

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


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
    assert payload["run"]["llm_status"] == "not_configured"
    assert payload["run"]["output"]["next_action"] == "send_campaign_details"
    assert payload["reply"]["processing_status"] == "suggestion_ready"
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
        creator = db.get(Creator, creator_id)
        assert creator is not None
        assert creator.current_status == "dropped"
        assert creator.do_not_contact_status == "pending_confirmation"
        assert creator.do_not_contact_reason == "explicit_opt_out"
        assert creator.do_not_contact_requested_at is not None
        assert db.scalar(
            select(func.count()).select_from(FollowupTask).where(FollowupTask.creator_id == creator_id)
        ) == 0


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
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context: ("not-json", "mocked"))

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
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context: (invalid_output, "mocked"))

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
    monkeypatch.setattr(services, "generate_raw_followup_output", lambda context: (low_confidence_output, "mocked"))

    response = client.post(
        "/api/followup-agent/simulate-reply",
        json={"creator_id": creator_id, "body": "Sounds interesting.", "run_agent": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reply"]["processing_status"] == "need_ai_review"


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
