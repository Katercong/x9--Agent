from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from desktop.backend.database.connection import SessionLocal, init_db
from desktop.backend.main import app
from desktop.backend.models.agent_followup_run import AgentFollowupRun
from desktop.backend.models.creator import Creator
from desktop.backend.models.creator_email_message import CreatorEmailMessage
from desktop.backend.models.creator_outreach_event import CreatorOutreachEvent
from desktop.backend.models.followup_task import FollowupTask
from desktop.backend.services import auth_service
from desktop.backend.utils.current_status import normalize_current_status


@pytest.fixture(scope="module", autouse=True)
def _init_desktop_db():
    init_db()


@pytest.fixture()
def desktop_client():
    with SessionLocal() as session:
        user = auth_service.upsert_user(
            session,
            username="followup_agent_api_user",
            email="followup-agent-api@example.com",
            password="TempPass123!",
            role="department_user",
            department_code="cross_border",
            approval_status=auth_service.ACTIVE_STATUS,
        )
        token, _ = auth_service.create_session_for_user(session, user, entry_scope="workspace")
    client = TestClient(app)
    client.cookies.set(auth_service.SESSION_COOKIE, token)
    return client


@pytest.fixture()
def api_creator():
    creator_id = "creator_followup_api_m5"
    with SessionLocal() as session:
        _cleanup_creator_rows(session, creator_id)
        session.add(
            Creator(
                id=creator_id,
                platform="tiktok",
                department_code="cross_border",
                handle="followup_api_test",
                display_name="Followup API Test",
                email="creator-api@example.com",
                has_email=1,
                current_status="contacted",
                recommendation_reason="Good fit for sample collaboration.",
                recommended_product_type="mom_baby",
                recommended_collab_type="sample_collab",
                owner_bd="Alice",
            )
        )
        session.commit()
    yield creator_id
    with SessionLocal() as session:
        _cleanup_creator_rows(session, creator_id)
        session.commit()


def test_simulate_reply_inserts_inbound_message_runs_agent_and_marks_followup(desktop_client, api_creator):
    """模块 5：模拟回复入库后可选立即运行 agent，并进入待跟进状态。"""
    response = desktop_client.post(
        "/api/local/followup-agent/simulate-reply",
        json={
            "creator_id": api_creator,
            "from_email": "creator-api@example.com",
            "subject": "Re: Collaboration",
            "body": "Sounds interesting. Can you send more campaign details?",
            "run_agent": True,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"]["creator_id"] == api_creator
    assert payload["message"]["direction"] == "inbound"
    assert payload["run"]["reply_category"] == "need_more_info"
    assert payload["run"]["llm_status"] == "not_configured"

    with SessionLocal() as session:
        message = session.get(CreatorEmailMessage, payload["message"]["id"])
        run = session.get(AgentFollowupRun, payload["run"]["id"])
        creator = session.get(Creator, api_creator)
        assert message is not None
        assert message.direction == "inbound"
        assert run is not None
        assert run.inbound_message_id == message.id
        assert creator is not None
        assert normalize_current_status(creator.current_status) == normalize_current_status("pending_followup")
        assert session.query(CreatorOutreachEvent).filter_by(creator_id=api_creator, event_type="pending_followup").count() >= 1
        assert session.query(FollowupTask).filter_by(creator_id=api_creator).count() >= 1


def test_run_agent_endpoint_persists_run_for_existing_inbound_message(desktop_client, api_creator):
    """模块 5：已有入站消息可以单独触发 agent run。"""
    inbound_id = "cem_followup_api_run_m5"
    with SessionLocal() as session:
        session.query(CreatorEmailMessage).filter_by(id=inbound_id).delete()
        session.add(
            CreatorEmailMessage(
                id=inbound_id,
                department_code="cross_border",
                creator_id=api_creator,
                gmail_account_id="gmail_followup_api",
                gmail_message_id="gmail_followup_api_run",
                direction="inbound",
                from_email="creator-api@example.com",
                to_email="bd@x9.com",
                subject="Re: Collaboration",
                body="What is your rate and commission?",
                body_format="plain",
                message_at=datetime(2026, 7, 11, 12, 0, 0),
            )
        )
        session.commit()

    response = desktop_client.post(
        "/api/local/followup-agent/runs",
        json={"inbound_message_id": inbound_id},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["run"]["inbound_message_id"] == inbound_id
    assert payload["run"]["reply_category"] == "negotiation"
    assert payload["run"]["output"]["next_action"] == "clarify_terms"


def test_followup_agent_run_list_and_detail_endpoints(desktop_client, api_creator):
    """模块 5：run 留痕需要能通过列表和详情接口查回。"""
    create = desktop_client.post(
        "/api/local/followup-agent/simulate-reply",
        json={
            "creator_id": api_creator,
            "from_email": "creator-api@example.com",
            "subject": "Re: Collaboration",
            "body": "Yes, sounds good.",
            "run_agent": True,
        },
    )
    run_id = create.json()["run"]["id"]

    detail = desktop_client.get(f"/api/local/followup-agent/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["run"]["id"] == run_id
    assert detail.json()["run"]["output"]["suggested_reply"]

    listed = desktop_client.get(f"/api/local/followup-agent/runs?creator_id={api_creator}&limit=20")
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()["items"]]
    assert run_id in ids


def _cleanup_creator_rows(session, creator_id: str) -> None:
    session.query(AgentFollowupRun).filter_by(creator_id=creator_id).delete()
    session.query(CreatorEmailMessage).filter_by(creator_id=creator_id).delete()
    session.query(CreatorOutreachEvent).filter_by(creator_id=creator_id).delete()
    session.query(FollowupTask).filter_by(creator_id=creator_id).delete()
    row = session.get(Creator, creator_id)
    if row is not None:
        session.delete(row)
