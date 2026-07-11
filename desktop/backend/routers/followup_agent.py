from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.agent_followup_run import AgentFollowupRun
from ..models.creator import Creator
from ..models.creator_email_message import CreatorEmailMessage
from ..services.departments import current_department_code, department_where, row_in_department
from ..services.followup_agent import (
    build_followup_context,
    generate_followup_suggestion,
    persist_followup_run,
)
from ..services.post_processing import create_outreach_event
from ..utils.id_utils import new_id


router = APIRouter(prefix="/api/local/followup-agent", tags=["followup-agent"])


class SimulateReplyIn(BaseModel):
    creator_id: str
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body: str = Field(min_length=1, max_length=20000)
    body_format: str = Field(default="plain", pattern="^(plain|html)$")
    run_agent: bool = True


class RunAgentIn(BaseModel):
    inbound_message_id: str


@router.post("/simulate-reply")
def simulate_reply(
    body: SimulateReplyIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """MVP 调试入口：模拟一条达人入站回复并可选立即运行 agent。"""

    creator = db.get(Creator, body.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(creator, current_department_code(request)):
        raise HTTPException(status_code=404, detail="creator not found")

    current_user = getattr(request.state, "current_user", None) or {}
    now = datetime.utcnow()
    message = CreatorEmailMessage(
        id=new_id("cem"),
        department_code=creator.department_code,
        creator_id=creator.id,
        gmail_account_id="simulated_followup_agent",
        gmail_message_id=new_id("gmail_sim"),
        gmail_thread_id=new_id("thread_sim"),
        direction="inbound",
        from_email=body.from_email or creator.email,
        to_email=body.to_email,
        subject=body.subject,
        snippet=body.body[:180],
        body_preview=body.body[:500],
        body=body.body,
        body_format=body.body_format,
        message_at=now,
        metadata_json=json.dumps({"source": "followup_agent_simulate_reply"}, ensure_ascii=False),
    )
    db.add(message)
    db.flush()

    create_outreach_event(
        db,
        creator,
        event_type="pending_followup",
        actor_user_id=current_user.get("id"),
        owner_bd=creator.owner_bd,
        note="Creator replied; follow-up agent simulation created an inbound message.",
        metadata={
            "source": "followup_agent_simulate_reply",
            "inbound_message_id": message.id,
            "gmail_thread_id": message.gmail_thread_id,
            "gmail_message_id": message.gmail_message_id,
        },
        event_at=now,
    )

    run_payload = None
    if body.run_agent:
        run = _create_agent_run(db, message.id, created_by=current_user.get("id"))
        run_payload = _run_to_dict(run)

    db.commit()
    return {
        "ok": True,
        "message": _message_to_dict(message),
        "run": run_payload,
    }


@router.post("/runs")
def run_agent(body: RunAgentIn, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _create_agent_run(
        db,
        body.inbound_message_id,
        created_by=(getattr(request.state, "current_user", None) or {}).get("id"),
    )
    db.commit()
    return {"ok": True, "run": _run_to_dict(run)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(AgentFollowupRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if not row_in_department(run, current_department_code(request)):
        raise HTTPException(status_code=404, detail="run not found")
    return {"ok": True, "run": _run_to_dict(run)}


@router.get("/runs")
def list_runs(
    request: Request,
    creator_id: str | None = Query(default=None),
    inbound_message_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = []
    where_department = department_where(AgentFollowupRun, current_department_code(request))
    if where_department is not None:
        filters.append(where_department)
    if creator_id:
        filters.append(AgentFollowupRun.creator_id == creator_id)
    if inbound_message_id:
        filters.append(AgentFollowupRun.inbound_message_id == inbound_message_id)

    total = int(db.scalar(select(func.count()).select_from(AgentFollowupRun).where(*filters)) or 0)
    rows = list(
        db.scalars(
            select(AgentFollowupRun)
            .where(*filters)
            .order_by(AgentFollowupRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return {
        "ok": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_run_to_dict(row) for row in rows],
    }


def _create_agent_run(db: Session, inbound_message_id: str, *, created_by: str | None) -> AgentFollowupRun:
    context = build_followup_context(db, inbound_message_id)
    suggestion, llm_status = generate_followup_suggestion(context)
    run = persist_followup_run(
        db,
        context=context,
        suggestion=suggestion,
        llm_status=llm_status,
        created_by=created_by,
    )
    db.flush()
    return run


def _message_to_dict(message: CreatorEmailMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "creator_id": message.creator_id,
        "direction": message.direction,
        "subject": message.subject,
        "body_preview": message.body_preview,
        "message_at": _iso(message.message_at),
    }


def _run_to_dict(run: AgentFollowupRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "department_code": run.department_code,
        "creator_id": run.creator_id,
        "inbound_message_id": run.inbound_message_id,
        "reply_category": run.reply_category,
        "suggested_status": run.suggested_status,
        "llm_status": run.llm_status,
        "context": _load_json(run.context_json),
        "output": _load_json(run.output_json),
        "validation_error": run.validation_error,
        "created_by": run.created_by,
        "created_at": _iso(run.created_at),
        "updated_at": _iso(run.updated_at),
    }


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
