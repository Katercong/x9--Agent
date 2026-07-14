from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import AgentFollowupRun, Creator, InboundReply, Product
from .schemas import (
    CreatorCreateIn,
    CreatorPatchIn,
    CreatorReplaceIn,
    ProductCreateIn,
    ProductPatchIn,
    ProductReplaceIn,
    RunAgentIn,
    SimulateReplyIn,
)
from .services import (
    classify_reply_result,
    ensure_pending_followup,
    handle_creator_declined,
    new_id,
    process_followup_reply,
)


app = FastAPI(title="X9 ReplyChat Agent", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "x9-replychat-agent"}


@app.post("/api/followup-agent/creators", status_code=201)
def create_creator(body: CreatorCreateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    creator = db.get(Creator, body.id)
    if creator is not None:
        raise HTTPException(status_code=409, detail="creator already exists")
    values = body.model_dump()
    creator = Creator(**values)
    db.add(creator)
    db.commit()
    db.refresh(creator)
    return {"ok": True, "creator": _creator_to_dict(creator)}


@app.put("/api/followup-agent/creators/{creator_id}")
def replace_creator(
    creator_id: str,
    body: CreatorReplaceIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    for key, value in body.model_dump().items():
        setattr(creator, key, value)
    db.commit()
    db.refresh(creator)
    return {"ok": True, "creator": _creator_to_dict(creator)}


@app.patch("/api/followup-agent/creators/{creator_id}")
def patch_creator(
    creator_id: str,
    body: CreatorPatchIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    # exclude_unset 能区分“字段未提供”和“调用方显式传 null”。
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(creator, key, value)
    db.commit()
    db.refresh(creator)
    return {"ok": True, "creator": _creator_to_dict(creator)}


@app.post("/api/followup-agent/products", status_code=201)
def create_product(body: ProductCreateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    existing = db.get(Product, body.id)
    duplicate_type = db.scalars(select(Product).where(Product.product_type == body.product_type).limit(1)).first()
    if existing is not None or duplicate_type is not None:
        raise HTTPException(status_code=409, detail="product id or product_type already exists")
    product = Product(**_product_values(body.model_dump()))
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"ok": True, "product": _product_to_dict(product)}


@app.put("/api/followup-agent/products/{product_id}")
def replace_product(
    product_id: str,
    body: ProductReplaceIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    _ensure_product_type_available(db, product_id, body.product_type)
    for key, value in _product_values(body.model_dump()).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return {"ok": True, "product": _product_to_dict(product)}


@app.patch("/api/followup-agent/products/{product_id}")
def patch_product(
    product_id: str,
    body: ProductPatchIn,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    updates = body.model_dump(exclude_unset=True)
    if "product_type" in updates and updates["product_type"] is not None:
        _ensure_product_type_available(db, product_id, str(updates["product_type"]))
    for key, value in _product_values(updates).items():
        setattr(product, key, value)
    db.commit()
    db.refresh(product)
    return {"ok": True, "product": _product_to_dict(product)}


@app.post("/api/followup-agent/simulate-reply")
def simulate_reply(body: SimulateReplyIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    creator = db.get(Creator, body.creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    message_fields = _normalized_message_fields(creator, body)
    existing_reply = _find_duplicate_reply(db, **message_fields)
    if existing_reply is not None:
        run_payload = _get_or_create_existing_run(db, existing_reply, body.run_agent)
        db.commit()
        return {"ok": True, "duplicate": True, "reply": _reply_to_dict(existing_reply), "run": run_payload}

    reply = InboundReply(
        id=new_id("ir"),
        **message_fields,
        body_format=body.body_format,
        message_at=datetime.utcnow(),
        metadata_json=json.dumps({"source": "simulate_reply"}, ensure_ascii=False),
    )
    db.add(reply)
    try:
        db.flush()
    except IntegrityError:
        # 业务预查后仍可能有并发请求先一步写入，回滚后返回已存在的同一回复。
        db.rollback()
        existing_reply = _find_duplicate_reply(db, **message_fields)
        if existing_reply is None:
            raise
        run_payload = _get_or_create_existing_run(db, existing_reply, body.run_agent)
        db.commit()
        return {"ok": True, "duplicate": True, "reply": _reply_to_dict(existing_reply), "run": run_payload}
    classification = classify_reply_result("\n".join([reply.subject or "", reply.body]))
    reply.reply_category = classification.reply_category
    reply.classification_confidence = classification.confidence
    reply.classification_reason = classification.reason
    reply.classified_at = datetime.utcnow()

    run_payload = None
    if classification.reply_category == "bounce_or_invalid":
        reply.processing_status = "ignored"
    elif classification.reply_category == "not_interested":
        handle_creator_declined(db, creator, reply)
        if body.run_agent:
            run = _create_run(db, reply.id)
            run_payload = _run_to_dict(run)
    else:
        ensure_pending_followup(db, creator, reply)
        if body.run_agent:
            run = _create_run(db, reply.id)
            run_payload = _run_to_dict(run)
    db.commit()
    return {"ok": True, "duplicate": False, "reply": _reply_to_dict(reply), "run": run_payload}


@app.post("/api/followup-agent/runs")
def run_agent(body: RunAgentIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    reply = db.get(InboundReply, body.inbound_reply_id)
    if reply is not None and reply.processing_status == "ignored":
        raise HTTPException(status_code=409, detail="ignored reply cannot run agent")
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
    return process_followup_reply(db, inbound_reply_id)


def _normalized_message_fields(creator: Creator, body: SimulateReplyIn) -> dict[str, str]:
    """统一可选邮件字段的空值，确保联合唯一约束不会被 NULL 绕过。"""

    return {
        "department_code": creator.department_code,
        "creator_id": creator.id,
        "direction": "inbound",
        "channel": "simulation",
        "from_email": body.from_email if body.from_email is not None else (creator.email or ""),
        "to_email": body.to_email or "",
        "subject": body.subject or "",
        "body": body.body,
    }


def _find_duplicate_reply(db: Session, **message_fields: str) -> InboundReply | None:
    return db.scalars(select(InboundReply).filter_by(**message_fields)).first()


def _get_or_create_existing_run(db: Session, reply: InboundReply, run_agent: bool) -> dict[str, Any] | None:
    if not run_agent or reply.processing_status == "ignored":
        return None
    run = db.scalars(
        select(AgentFollowupRun)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .order_by(AgentFollowupRun.created_at.desc())
        .limit(1)
    ).first()
    if run is None:
        run = _create_run(db, reply.id)
    return _run_to_dict(run)


def _creator_to_dict(row: Creator) -> dict[str, Any]:
    return {
        "id": row.id,
        "handle": row.handle,
        "display_name": row.display_name,
        "current_status": row.current_status,
        "do_not_contact_status": row.do_not_contact_status,
    }


def _product_values(values: dict[str, Any]) -> dict[str, Any]:
    """把接口中的列表字段转换为数据库保存的 JSON 文本。"""

    converted = dict(values)
    if "selling_points" in converted:
        converted["selling_points_json"] = json.dumps(converted.pop("selling_points") or [], ensure_ascii=False)
    if "forbidden_claims" in converted:
        converted["forbidden_claims_json"] = json.dumps(converted.pop("forbidden_claims") or [], ensure_ascii=False)
    return converted


def _ensure_product_type_available(db: Session, product_id: str, product_type: str) -> None:
    existing = db.scalars(select(Product).where(Product.product_type == product_type).limit(1)).first()
    if existing is not None and existing.id != product_id:
        raise HTTPException(status_code=409, detail="product_type already exists")


def _product_to_dict(row: Product) -> dict[str, Any]:
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
        "is_active": row.is_active,
    }


def _load_json_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except ValueError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _reply_to_dict(row: InboundReply) -> dict[str, Any]:
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
        "prompt_version": row.prompt_version,
        "rendered_prompt": row.rendered_prompt,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None
