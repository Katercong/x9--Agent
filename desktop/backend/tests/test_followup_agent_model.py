from __future__ import annotations

import importlib

import pytest
from sqlalchemy import inspect

from x9_creator_desktop_system.backend.database.connection import SessionLocal, engine


def _agent_followup_run_model():
    try:
        module = importlib.import_module(
            "x9_creator_desktop_system.backend.models.agent_followup_run"
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"AgentFollowupRun model should exist: {exc}")
    return module.AgentFollowupRun


def test_agent_followup_runs_table_is_registered_by_init_db():
    """模块 2：init_db 后必须能看到 agent 运行留痕表。"""
    _agent_followup_run_model()

    db_inspector = inspect(engine)
    assert db_inspector.has_table("agent_followup_runs")
    columns = {column["name"] for column in db_inspector.get_columns("agent_followup_runs")}

    assert {
        "id",
        "department_code",
        "creator_id",
        "inbound_message_id",
        "reply_category",
        "suggested_status",
        "llm_status",
        "context_json",
        "output_json",
        "validation_error",
        "created_by",
        "created_at",
        "updated_at",
    } <= columns


def test_agent_followup_run_model_can_roundtrip_trace_fields():
    """模块 2：run 留痕字段需要能写入并读取，先不接入真实 LLM。"""
    AgentFollowupRun = _agent_followup_run_model()
    run_id = "afr_module2_roundtrip"

    with SessionLocal() as session:
        session.query(AgentFollowupRun).filter_by(id=run_id).delete()
        session.add(
            AgentFollowupRun(
                id=run_id,
                department_code="cross_border",
                creator_id="creator_module2",
                inbound_message_id="cem_module2",
                reply_category="need_more_info",
                suggested_status="pending_followup",
                llm_status="not_configured",
                context_json='{"message":"Can you send details?"}',
                output_json='{"next_action":"send_campaign_details"}',
                created_by="module2_test",
            )
        )
        session.commit()

        saved = session.get(AgentFollowupRun, run_id)
        assert saved is not None
        assert saved.creator_id == "creator_module2"
        assert saved.inbound_message_id == "cem_module2"
        assert saved.reply_category == "need_more_info"
        assert saved.suggested_status == "pending_followup"
        assert saved.llm_status == "not_configured"
        assert saved.context_json and "Can you send details?" in saved.context_json
        assert saved.output_json and "send_campaign_details" in saved.output_json

        session.delete(saved)
        session.commit()


def test_agent_followup_runs_are_exposed_through_local_data_api(client):
    """模块 2：通用只读数据接口需要能查 agent_followup_runs。"""
    AgentFollowupRun = _agent_followup_run_model()
    run_id = "afr_module2_data_api"

    with SessionLocal() as session:
        session.query(AgentFollowupRun).filter_by(id=run_id).delete()
        session.add(
            AgentFollowupRun(
                id=run_id,
                department_code="cross_border",
                creator_id="creator_module2_api",
                inbound_message_id="cem_module2_api",
                reply_category="interested",
                suggested_status="pending_followup",
                llm_status="not_configured",
                context_json='{"source":"test"}',
                output_json='{"suggested_reply":"Thanks for replying."}',
                created_by="module2_test",
            )
        )
        session.commit()

    try:
        response = client.get(
            "/api/local/data/agent_followup_runs?creator_id=creator_module2_api&limit=5"
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["resource"] == "agent_followup_runs"
        assert payload["total"] == 1
        assert payload["items"][0]["id"] == run_id
        assert payload["items"][0]["reply_category"] == "interested"
    finally:
        with SessionLocal() as session:
            session.query(AgentFollowupRun).filter_by(id=run_id).delete()
            session.commit()
