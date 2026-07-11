from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import AgentFollowupRun, Creator, InboundReply
from .schemas import CreatorIn, RunAgentIn, SimulateReplyIn
from .services import (
    build_followup_context,
    classify_reply_result,
    ensure_pending_followup,
    generate_followup_suggestion,
    new_id,
    persist_followup_run,
)


app = FastAPI(title="X9 ReplyChat Agent", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "x9-replychat-agent"}


@app.post("/api/followup-agent/creators")
def upsert_creator(body: CreatorIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    creator = db.get(Creator, body.id)
    if creator is None:
        creator = Creator(id=body.id, handle=body.handle)
        db.add(creator)
    for key, value in body.model_dump().items():
        setattr(creator, key, value)
    db.commit()
    db.refresh(creator)
    return {"ok": True, "creator": _creator_to_dict(creator)}


@app.post("/api/followup-agent/simulate-reply")
def simulate_reply(body: SimulateReplyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    creator = db.get(Creator, body.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    reply = InboundReply(
        id=new_id("ir"),
        department_code=creator.department_code,
        creator_id=creator.id,
        direction="inbound",
        from_email=body.from_email or creator.email,
        to_email=body.to_email,
        subject=body.subject,
        body=body.body,
        body_format=body.body_format,
        message_at=datetime.utcnow(),
        metadata_json=json.dumps({"source": "simulate_reply"}, ensure_ascii=False),
    )
    db.add(reply)
    db.flush()
    classification = classify_reply_result("\n".join([reply.subject or "", reply.body]))
    reply.reply_category = classification.reply_category
    reply.classification_confidence = classification.confidence
    reply.classification_reason = classification.reason
    reply.classified_at = datetime.utcnow()

    run_payload = None
    if classification.reply_category == "bounce_or_invalid":
        reply.processing_status = "ignored"
    else:
        ensure_pending_followup(db, creator, reply)
        if body.run_agent:
            run = _create_run(db, reply.id)
            run_payload = _run_to_dict(run)
    db.commit()
    return {"ok": True, "reply": _reply_to_dict(reply), "run": run_payload}


@app.post("/api/followup-agent/runs")
def run_agent(body: RunAgentIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = _create_run(db, body.inbound_reply_id)
    db.commit()
    return {"ok": True, "run": _run_to_dict(run)}


@app.get("/api/followup-agent/replies/{reply_id}")
def get_reply(reply_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    reply = db.get(InboundReply, reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    return {"ok": True, "reply": _reply_to_dict(reply)}


@app.get("/api/followup-agent/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(AgentFollowupRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {"ok": True, "run": _run_to_dict(run)}


@app.get("/api/followup-agent/runs")
def list_runs(
    creator_id: str | None = Query(default=None),
    inbound_reply_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = []
    if creator_id:
        filters.append(AgentFollowupRun.creator_id == creator_id)
    if inbound_reply_id:
        filters.append(AgentFollowupRun.inbound_reply_id == inbound_reply_id)
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
    return {"ok": True, "total": total, "items": [_run_to_dict(row) for row in rows]}


def _create_run(db: Session, inbound_reply_id: str) -> AgentFollowupRun:
    context = build_followup_context(db, inbound_reply_id)
    suggestion, llm_status = generate_followup_suggestion(context)
    run = persist_followup_run(db, context=context, suggestion=suggestion, llm_status=llm_status)
    reply = db.get(InboundReply, inbound_reply_id)
    if reply is not None and reply.processing_status != "ignored":
        rule_confidence = reply.classification_confidence or 0.0
        reply.processing_status = "need_ai_review" if min(rule_confidence, suggestion.confidence) < 0.70 else "suggestion_ready"
        db.flush()
    return run


def _creator_to_dict(row: Creator) -> dict[str, Any]:
    return {"id": row.id, "handle": row.handle, "display_name": row.display_name, "current_status": row.current_status}


def _reply_to_dict(row: InboundReply) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "direction": row.direction,
        "from_email": row.from_email,
        "to_email": row.to_email,
        "subject": row.subject,
        "body": row.body,
        "body_format": row.body_format,
        "message_at": row.message_at.isoformat() if row.message_at else None,
        "processing_status": row.processing_status,
        "reply_category": row.reply_category,
        "classification_confidence": row.classification_confidence,
        "classification_reason": row.classification_reason,
        "classified_at": row.classified_at.isoformat() if row.classified_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _run_to_dict(row: AgentFollowupRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "inbound_reply_id": row.inbound_reply_id,
        "reply_category": row.reply_category,
        "suggested_status": row.suggested_status,
        "llm_status": row.llm_status,
        "context": _load_json(row.context_json),
        "output": _load_json(row.output_json),
        "validation_error": row.validation_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None
