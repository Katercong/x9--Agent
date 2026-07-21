from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import (
    AgentFollowupRun,
    Creator,
    DoNotContactConfirmation,
    DraftExportRecord,
    HumanReviewDecision,
    InboundReply,
    Product,
    ReferenceMaterial,
    SimulatedOutboundInstruction,
)
from .schemas import (
    CreatorCreateIn,
    CreatorPatchIn,
    CreatorReplaceIn,
    DraftExportCreateIn,
    HumanReviewDecisionCreateIn,
    ProductCreateIn,
    ProductPatchIn,
    ProductReplaceIn,
    ReferenceMaterialCreateIn,
    ReferenceMaterialVersionIn,
    RunAgentIn,
    SimulateReplyIn,
)
from .services import (
    classify_reply_result,
    enqueue_followup_run,
    ensure_pending_followup,
    handle_creator_declined,
    is_creator_contact_blocked,
    is_automatic_generation_eligible,
    new_id,
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


@app.post("/api/followup-agent/reference-materials", status_code=201)
def create_reference_material(body: ReferenceMaterialCreateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """创建首个参考资料版本，并将同一资料键的旧活动版本停用。"""

    version = int(db.scalar(select(func.max(ReferenceMaterial.version)).where(ReferenceMaterial.reference_key == body.reference_key)) or 0) + 1
    db.query(ReferenceMaterial).filter(ReferenceMaterial.reference_key == body.reference_key).update({"is_active": False})
    row = ReferenceMaterial(id=new_id("ref"), version=version, is_active=True, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "reference_material": _reference_material_to_dict(row)}


@app.patch("/api/followup-agent/reference-materials/{reference_key}")
def version_reference_material(reference_key: str, body: ReferenceMaterialVersionIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """以新增版本替代当前活动资料，保留旧版本供历史 run 追溯。"""

    exists = db.scalar(select(ReferenceMaterial.id).where(ReferenceMaterial.reference_key == reference_key).limit(1))
    if exists is None:
        raise HTTPException(status_code=404, detail="reference material not found")
    version = int(db.scalar(select(func.max(ReferenceMaterial.version)).where(ReferenceMaterial.reference_key == reference_key)) or 0) + 1
    db.query(ReferenceMaterial).filter(ReferenceMaterial.reference_key == reference_key).update({"is_active": False})
    row = ReferenceMaterial(id=new_id("ref"), reference_key=reference_key, version=version, is_active=True, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "reference_material": _reference_material_to_dict(row)}


@app.get("/api/followup-agent/reference-materials")
def list_reference_materials(active_only: bool = Query(default=False), db: Session = Depends(get_db)) -> dict[str, Any]:
    """按版本列出参考资料，可选择只查看当前启用版本。"""

    query = select(ReferenceMaterial)
    if active_only:
        query = query.where(ReferenceMaterial.is_active.is_(True))
    rows = list(db.scalars(query.order_by(ReferenceMaterial.reference_key.asc(), ReferenceMaterial.version.desc())).all())
    return {"ok": True, "items": [_reference_material_to_dict(row) for row in rows]}


@app.get("/api/followup-agent/outbound-instructions")
def list_outbound_instructions(creator_id: str | None = Query(default=None), db: Session = Depends(get_db)) -> dict[str, Any]:
    """查询内部模拟出站指令，当前接口不会触发任何外部渠道发送。"""

    query = select(SimulatedOutboundInstruction)
    if creator_id:
        query = query.where(SimulatedOutboundInstruction.creator_id == creator_id)
    rows = list(db.scalars(query.order_by(SimulatedOutboundInstruction.created_at.desc())).all())
    return {"ok": True, "total": len(rows), "items": [{"id": row.id, "creator_id": row.creator_id, "inbound_reply_id": row.inbound_reply_id, "action_type": row.action_type, "template_key": row.template_key, "content": row.content, "status": row.status} for row in rows]}


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
    if is_creator_contact_blocked(creator):
        # DNC 待确认时已停止 AI 和导出；后续消息只保留为审计，不再进入业务跟进队列。
        reply.processing_status = "dnc_blocked"
    elif classification.reply_category == "bounce_or_invalid":
        reply.processing_status = "ignored"
    elif classification.reply_category == "not_interested":
        handle_creator_declined(db, creator, reply)
    else:
        ensure_pending_followup(db, creator, reply)
        if body.run_agent:
            if is_automatic_generation_eligible(db, reply):
                run = _create_run(db, reply.id, created_by="automatic")
                run_payload = _run_to_dict(run)
            else:
                # 即使不调用模型，也必须让人工知道该回复需要处理。
                reply.processing_status = "need_ai_review"
    db.commit()
    return {"ok": True, "duplicate": False, "reply": _reply_to_dict(reply), "run": run_payload}


@app.post("/api/followup-agent/runs")
def run_agent(body: RunAgentIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    reply = db.get(InboundReply, body.inbound_reply_id)
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    if reply.processing_status == "ignored":
        raise HTTPException(status_code=409, detail="ignored reply cannot run agent")
    if reply.processing_status == "reviewed":
        raise HTTPException(status_code=409, detail="reviewed reply cannot run agent")
    if reply.reply_category == "not_interested":
        raise HTTPException(status_code=409, detail="terminal reply cannot run agent")
    creator = db.get(Creator, reply.creator_id)
    if is_creator_contact_blocked(creator):
        raise HTTPException(status_code=409, detail="do not contact creator cannot run agent")
    run = _create_run(db, body.inbound_reply_id, created_by="manual")
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


@app.get("/api/followup-agent/review-queue")
def list_human_review_queue(
    department_code: str | None = Query(default=None),
    review_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """列出普通、拒绝和 DNC 待审项；终态项当前只读，不提供确认写操作。"""

    allowed_review_types = {"standard", "decline", "dnc_confirmation"}
    if review_type is not None and review_type not in allowed_review_types:
        raise HTTPException(status_code=422, detail="unknown review_type")
    filters = [InboundReply.processing_status == "need_ai_review"]
    if department_code:
        filters.append(InboundReply.department_code == department_code)
    replies = list(
        db.scalars(
            select(InboundReply)
            .where(*filters)
            .order_by(InboundReply.created_at.desc(), InboundReply.id.desc())
        ).all()
    )
    items = []
    for reply in replies:
        latest_run = db.scalars(
            select(AgentFollowupRun)
            .where(AgentFollowupRun.inbound_reply_id == reply.id)
            .order_by(AgentFollowupRun.created_at.desc(), AgentFollowupRun.id.desc())
            .limit(1)
        ).first()
        dnc_confirmation = db.scalars(
            select(DoNotContactConfirmation)
            .where(DoNotContactConfirmation.inbound_reply_id == reply.id)
            .where(DoNotContactConfirmation.status == "pending_confirmation")
            .limit(1)
        ).first()
        if dnc_confirmation is not None:
            item_review_type = "dnc_confirmation"
        elif reply.reply_category == "not_interested":
            item_review_type = "decline"
        else:
            item_review_type = "standard"
        if review_type is not None and item_review_type != review_type:
            continue
        # 终态项保留在队列中供审核人查看，但 RBAC 完成前不允许由本接口作出决定。
        decision_available = (
            item_review_type == "standard"
            and latest_run is not None
            and latest_run.execution_status in {"succeeded", "failed"}
        )
        items.append(
            {
                "review_type": item_review_type,
                "decision_available": decision_available,
                "reply": _reply_to_dict(reply),
                "run": _run_to_dict(latest_run) if latest_run is not None else None,
                "dnc_confirmation": _dnc_confirmation_to_dict(dnc_confirmation) if dnc_confirmation else None,
            }
        )
    total = len(items)
    return {"ok": True, "total": total, "items": items[offset : offset + limit]}


@app.post("/api/followup-agent/review-decisions", status_code=201)
def create_human_review_decision(
    body: HumanReviewDecisionCreateIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """保存普通回复的最终人工决定，不自动推进达人业务状态。"""

    run = db.get(AgentFollowupRun, body.agent_followup_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="agent followup run not found")
    if run.execution_status not in {"succeeded", "failed"}:
        raise HTTPException(status_code=409, detail="agent followup run is not finished")
    reply = db.get(InboundReply, run.inbound_reply_id)
    if reply is None:
        raise HTTPException(status_code=409, detail="agent followup run has no inbound reply")
    if reply.processing_status != "need_ai_review":
        raise HTTPException(status_code=409, detail="reply is not pending human review")
    if reply.reply_category in {"not_interested", "bounce_or_invalid"}:
        raise HTTPException(status_code=409, detail="terminal reply cannot use standard review decision")
    active_run = db.scalar(
        select(AgentFollowupRun.id)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .where(AgentFollowupRun.execution_status.in_(("queued", "running")))
        .limit(1)
    )
    if active_run is not None:
        raise HTTPException(status_code=409, detail="reply has an active agent followup run")
    latest_run = db.scalars(
        select(AgentFollowupRun)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .order_by(AgentFollowupRun.created_at.desc(), AgentFollowupRun.id.desc())
        .limit(1)
    ).first()
    if latest_run is None or latest_run.id != run.id:
        raise HTTPException(status_code=409, detail="only the latest agent followup run can be reviewed")
    if db.scalar(select(HumanReviewDecision.id).where(HumanReviewDecision.agent_followup_run_id == run.id)) is not None:
        raise HTTPException(status_code=409, detail="agent followup run already has a human review decision")

    # actor_id 当前仅是审计归属；正式身份认证与角色授权将在后续 RBAC 模块接管。
    decision = HumanReviewDecision(
        id=new_id("hrd"),
        department_code=reply.department_code,
        creator_id=reply.creator_id,
        inbound_reply_id=reply.id,
        agent_followup_run_id=run.id,
        outcome=body.outcome,
        final_draft=body.final_draft.strip() if body.final_draft is not None else None,
        note=body.note,
        actor_id=body.actor_id,
    )
    db.add(decision)
    # 人工审核完成只结束本次回复的审核，不采纳模型 suggested_status，也不修改达人业务状态。
    reply.processing_status = "reviewed"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="inbound reply already has a human review decision")
    db.refresh(decision)
    db.refresh(reply)
    return {"ok": True, "decision": _human_review_decision_to_dict(decision), "reply": _reply_to_dict(reply)}


@app.get("/api/followup-agent/review-decisions/{decision_id}")
def get_human_review_decision(decision_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """读取不可变审核决定及其导出审计，不触发复制、导出或发送。"""

    decision = db.get(HumanReviewDecision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="human review decision not found")
    exports = list(
        db.scalars(
            select(DraftExportRecord)
            .where(DraftExportRecord.human_review_decision_id == decision.id)
            .order_by(DraftExportRecord.exported_at.desc(), DraftExportRecord.id.desc())
        ).all()
    )
    return {
        "ok": True,
        "decision": _human_review_decision_to_dict(decision),
        "exports": [_draft_export_record_to_dict(row) for row in exports],
    }


@app.post("/api/followup-agent/review-decisions/{decision_id}/exports", status_code=201)
def create_draft_export_record(
    decision_id: str, body: DraftExportCreateIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """记录人工导出草稿的快照；该接口绝不调用外部渠道。"""

    decision = db.get(HumanReviewDecision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="human review decision not found")
    if decision.outcome != "approve_draft" or not decision.final_draft:
        raise HTTPException(status_code=409, detail="human review decision has no approved draft")
    creator = db.get(Creator, decision.creator_id)
    if is_creator_contact_blocked(creator):
        raise HTTPException(status_code=409, detail="do not contact creator cannot export draft")

    export = DraftExportRecord(
        id=new_id("der"),
        department_code=decision.department_code,
        human_review_decision_id=decision.id,
        creator_id=decision.creator_id,
        inbound_reply_id=decision.inbound_reply_id,
        exported_content=decision.final_draft,
        actor_id=body.actor_id,
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return {"ok": True, "export": _draft_export_record_to_dict(export)}


def _create_run(db: Session, inbound_reply_id: str, *, created_by: str) -> AgentFollowupRun:
    return enqueue_followup_run(db, inbound_reply_id, created_by=created_by)


def _normalized_message_fields(creator: Creator, body: SimulateReplyIn) -> dict[str, str]:
    """规范化模拟消息字段，并生成可重放的稳定外部消息 ID。"""

    fields = {
        "department_code": creator.department_code,
        "creator_id": creator.id,
        "direction": "inbound",
        "channel": "simulation",
        "from_email": body.from_email if body.from_email is not None else (creator.email or ""),
        "to_email": body.to_email or "",
        "subject": body.subject or "",
        "body": body.body,
    }
    fields["external_message_id"] = _simulation_external_message_id(fields)
    return fields


def _simulation_external_message_id(message_fields: dict[str, str]) -> str:
    """Derive a deterministic replay key for simulated inbound messages."""

    replay_key = json.dumps(message_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"simulation:{sha256(replay_key.encode('utf-8')).hexdigest()}"


def _find_duplicate_reply(db: Session, **message_fields: str) -> InboundReply | None:
    return db.scalars(select(InboundReply).filter_by(**message_fields)).first()


def _get_or_create_existing_run(db: Session, reply: InboundReply, run_agent: bool) -> dict[str, Any] | None:
    if not run_agent or reply.processing_status in {"ignored", "reviewed"}:
        return None
    if is_creator_contact_blocked(db.get(Creator, reply.creator_id)):
        return None
    run = db.scalars(
        select(AgentFollowupRun)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .order_by(AgentFollowupRun.created_at.desc())
        .limit(1)
    ).first()
    if run is None and is_automatic_generation_eligible(db, reply):
        run = _create_run(db, reply.id, created_by="automatic")
    return _run_to_dict(run) if run is not None else None


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
        "block_reason": row.block_reason,
        "execution_status": row.execution_status,
        "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
        "provider_model": row.provider_model,
        "context": _load_json(row.context_json),
        "output": _load_json(row.output_json),
        "validation_error": row.validation_error,
        "prompt_version": row.prompt_version,
        "rendered_prompt": row.rendered_prompt,
        "reference_materials": _load_json(row.reference_materials_json) or [],
        "error_summary": row.error_summary,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "prompt_characters": row.prompt_characters,
        "output_characters": row.output_characters,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _human_review_decision_to_dict(row: HumanReviewDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "inbound_reply_id": row.inbound_reply_id,
        "agent_followup_run_id": row.agent_followup_run_id,
        "outcome": row.outcome,
        "final_draft": row.final_draft,
        "note": row.note,
        "actor_id": row.actor_id,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _draft_export_record_to_dict(row: DraftExportRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "human_review_decision_id": row.human_review_decision_id,
        "creator_id": row.creator_id,
        "inbound_reply_id": row.inbound_reply_id,
        "exported_content": row.exported_content,
        "actor_id": row.actor_id,
        "exported_at": row.exported_at.isoformat() if row.exported_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "delivery_status": "not_sent_by_system",
    }


def _dnc_confirmation_to_dict(row: DoNotContactConfirmation) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "inbound_reply_id": row.inbound_reply_id,
        "reason": row.reason,
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _load_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _reference_material_to_dict(row: ReferenceMaterial) -> dict[str, Any]:
    """将资料版本转换为接口返回结构，避免直接暴露 ORM 对象。"""

    return {"id": row.id, "reference_key": row.reference_key, "version": row.version, "scope": row.scope, "material_type": row.material_type, "product_type": row.product_type, "title": row.title, "content": row.content, "is_active": row.is_active}
