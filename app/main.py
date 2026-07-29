from __future__ import annotations

import json
from hashlib import sha256
from datetime import datetime
from pathlib import Path
from collections.abc import Collection
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, case, func, or_, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from .database import get_db, init_db
from .identity import ensure_capability, get_current_principal
from .models import (
    AgentFollowupRun,
    AuthUser,
    AuthorizationAuditEvent,
    Creator,
    CreatorOutreachEvent,
    Department,
    DoNotContactConfirmation,
    DraftExportRecord,
    FollowupTask,
    HumanReviewDecision,
    InboundReply,
    Product,
    ReferenceMaterial,
    SimulatedOutboundInstruction,
    UserDepartmentMembership,
)
from .authorization import Capability, Principal, Role
from .schemas import (
    AccessDepartmentCreateIn,
    AccessDepartmentPatchIn,
    AccessMembershipCreateIn,
    AccessMembershipPatchIn,
    AccessUserCreateIn,
    AccessUserPatchIn,
    CreatorCreateIn,
    CreatorPatchIn,
    CreatorReplaceIn,
    DncConfirmationApproveIn,
    DncConfirmationRejectIn,
    DraftExportCreateIn,
    FailedReviewRetryIn,
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
    build_followup_context,
    classify_reply_result,
    enqueue_followup_run,
    ensure_pending_followup,
    handle_creator_declined,
    is_creator_contact_blocked,
    is_automatic_generation_eligible,
    new_id,
)


app = FastAPI(title="X9 ReplyChat Agent", version="0.1.0")

OPERATOR_WORKBENCH_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
app.mount(
    "/operator-workbench",
    StaticFiles(directory=str(OPERATOR_WORKBENCH_DIST), html=True, check_dir=False),
    name="operator-workbench",
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "x9-replychat-agent"}


@app.get("/api/followup-agent/auth/me")
def get_auth_me(principal: Principal = Depends(get_current_principal)) -> dict[str, object]:
    """Expose only Agent-local RBAC scope; never disclose X9 assertions or secrets."""

    return {
        "user_id": principal.user_id,
        "display_name": principal.display_name,
        "departments": [
            {"code": membership.department_code, "role": membership.role.value}
            for membership in principal.memberships
        ],
        "capabilities": sorted(
            {
                capability.value
                for capability in Capability
                if principal.allowed_departments_for(capability)
            }
        ),
    }


@app.get("/api/followup-agent/access/departments")
def list_access_departments(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """List only departments the current administrator may manage."""

    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    departments = db.scalars(
        select(Department)
        .where(Department.code.in_(allowed_departments))
        .order_by(Department.code.asc())
    ).all()
    return {"items": [_department_to_dict(department) for department in departments]}


@app.post("/api/followup-agent/access/departments", status_code=201)
def create_access_department(
    body: AccessDepartmentCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Create a department and grant its creator an active admin membership."""

    _allowed_departments(principal, Capability.ACCESS_MANAGE)
    code = _normalise_department_code(body.code)
    if db.scalar(select(Department.id).where(Department.code == code)) is not None:
        raise HTTPException(status_code=409, detail="department already exists")
    actor = _current_auth_user_or_503(db, principal)
    department = Department(
        id=new_id("department"),
        code=code,
        name=body.name.strip(),
        is_active=True,
    )
    db.add(department)
    db.flush()
    membership = UserDepartmentMembership(
        id=new_id("membership"),
        auth_user_id=actor.id,
        department_id=department.id,
        role=Role.ADMIN.value,
        is_active=True,
        authorization_source="admin_api_department_creator",
        granted_by_auth_user_id=actor.id,
    )
    db.add(membership)
    _append_authorization_audit(
        db,
        action="access_department_created",
        actor_auth_user_id=actor.id,
        department_id=department.id,
        after=_department_snapshot(department),
    )
    _append_authorization_audit(
        db,
        action="access_membership_created",
        actor_auth_user_id=actor.id,
        target_auth_user_id=actor.id,
        department_id=department.id,
        after=_membership_snapshot(membership, department.code),
    )
    db.commit()
    db.refresh(department)
    db.refresh(membership)
    return {
        "ok": True,
        "department": _department_to_dict(department),
        "membership": _membership_to_dict(membership, department),
    }


@app.patch("/api/followup-agent/access/departments/{department_code}")
def patch_access_department(
    department_code: str,
    body: AccessDepartmentPatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Soft-update a department within the current administrator's scope."""

    department = _managed_department_or_404(db, department_code, principal)
    actor = _current_auth_user_or_503(db, principal)
    before = _department_snapshot(department)
    if "name" in body.model_fields_set and body.name is not None:
        department.name = body.name.strip()
    if "is_active" in body.model_fields_set:
        department.is_active = body.is_active
    _append_authorization_audit(
        db,
        action="access_department_updated",
        actor_auth_user_id=actor.id,
        department_id=department.id,
        before=before,
        after=_department_snapshot(department),
    )
    db.commit()
    db.refresh(department)
    return {"ok": True, "department": _department_to_dict(department)}


@app.get("/api/followup-agent/access/users")
def list_access_users(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """List mappings that do not carry memberships outside the administrator's scope."""

    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    foreign_memberships = (
        select(UserDepartmentMembership.auth_user_id)
        .join(Department, Department.id == UserDepartmentMembership.department_id)
        .where(Department.code.not_in(allowed_departments))
    )
    users = db.scalars(
        select(AuthUser)
        .join(UserDepartmentMembership, UserDepartmentMembership.auth_user_id == AuthUser.id)
        .join(Department, Department.id == UserDepartmentMembership.department_id)
        .where(
            Department.code.in_(allowed_departments),
            AuthUser.id.not_in(foreign_memberships),
        )
        .distinct()
        .order_by(AuthUser.created_at.desc(), AuthUser.id.desc())
    ).all()
    return {"items": [_auth_user_to_dict(user) for user in users]}


@app.post("/api/followup-agent/access/users", status_code=201)
def create_access_user(
    body: AccessUserCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Provision an Agent-local identity mapping; it has no access until membership is granted."""

    _allowed_departments(principal, Capability.ACCESS_MANAGE)
    source = body.identity_source.strip().lower()
    subject = body.external_subject.strip()
    if db.scalar(
        select(AuthUser.id).where(
            AuthUser.identity_source == source,
            AuthUser.external_subject == subject,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="auth user already exists")
    actor = _current_auth_user_or_503(db, principal)
    user = AuthUser(
        id=new_id("auth_user"),
        identity_source=source,
        external_subject=subject,
        display_name=body.display_name.strip() if body.display_name and body.display_name.strip() else None,
        is_active=True,
    )
    db.add(user)
    _append_authorization_audit(
        db,
        action="access_user_created",
        actor_auth_user_id=actor.id,
        target_auth_user_id=user.id,
        after=_auth_user_snapshot(user),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="auth user already exists") from exc
    db.refresh(user)
    return {"ok": True, "user": _auth_user_to_dict(user)}


@app.patch("/api/followup-agent/access/users/{auth_user_id}")
def patch_access_user(
    auth_user_id: str,
    body: AccessUserPatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Change local display metadata or immediately revoke a scoped user by soft-disable."""

    user = _managed_auth_user_or_404(db, auth_user_id, principal)
    actor = _current_auth_user_or_503(db, principal)
    before = _auth_user_snapshot(user)
    if "display_name" in body.model_fields_set:
        user.display_name = body.display_name.strip() if body.display_name and body.display_name.strip() else None
    if "is_active" in body.model_fields_set:
        user.is_active = body.is_active
    _append_authorization_audit(
        db,
        action="access_user_updated",
        actor_auth_user_id=actor.id,
        target_auth_user_id=user.id,
        before=before,
        after=_auth_user_snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return {"ok": True, "user": _auth_user_to_dict(user)}


@app.get("/api/followup-agent/access/memberships")
def list_access_memberships(
    department_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """List only memberships for departments the current administrator may manage."""

    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    statement = (
        select(UserDepartmentMembership, Department)
        .join(Department, Department.id == UserDepartmentMembership.department_id)
        .where(Department.code.in_(allowed_departments))
        .order_by(Department.code.asc(), UserDepartmentMembership.created_at.asc(), UserDepartmentMembership.id.asc())
    )
    if department_code is not None:
        statement = statement.where(Department.code == _normalise_department_code(department_code))
    rows = db.execute(statement).all()
    return {"items": [_membership_to_dict(membership, department) for membership, department in rows]}


@app.post("/api/followup-agent/access/memberships", status_code=201)
def create_access_membership(
    body: AccessMembershipCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Grant one role in one scoped department; existing relations are only reactivated by PATCH."""

    department = _managed_department_or_404(db, body.department_code, principal)
    user = _managed_auth_user_or_404(db, body.auth_user_id, principal, allow_unassigned=True)
    existing = db.scalar(
        select(UserDepartmentMembership).where(
            UserDepartmentMembership.auth_user_id == user.id,
            UserDepartmentMembership.department_id == department.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="department membership already exists")
    actor = _current_auth_user_or_503(db, principal)
    membership = UserDepartmentMembership(
        id=new_id("membership"),
        auth_user_id=user.id,
        department_id=department.id,
        role=Role(body.role).value,
        is_active=True,
        authorization_source="admin_api",
        granted_by_auth_user_id=actor.id,
    )
    db.add(membership)
    _append_authorization_audit(
        db,
        action="access_membership_created",
        actor_auth_user_id=actor.id,
        target_auth_user_id=user.id,
        department_id=department.id,
        after=_membership_snapshot(membership, department.code),
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="department membership already exists") from exc
    db.refresh(membership)
    return {"ok": True, "membership": _membership_to_dict(membership, department)}


@app.patch("/api/followup-agent/access/memberships/{membership_id}")
def patch_access_membership(
    membership_id: str,
    body: AccessMembershipPatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Change a scoped membership role or soft-disable it for immediate revocation."""

    membership, department = _managed_membership_or_404(db, membership_id, principal)
    actor = _current_auth_user_or_503(db, principal)
    before = _membership_snapshot(membership, department.code)
    if "role" in body.model_fields_set and body.role is not None:
        membership.role = Role(body.role).value
    if "is_active" in body.model_fields_set:
        membership.is_active = body.is_active
    _append_authorization_audit(
        db,
        action="access_membership_updated",
        actor_auth_user_id=actor.id,
        target_auth_user_id=membership.auth_user_id,
        department_id=department.id,
        before=before,
        after=_membership_snapshot(membership, department.code),
    )
    db.commit()
    db.refresh(membership)
    return {"ok": True, "membership": _membership_to_dict(membership, department)}


@app.get("/api/followup-agent/access/audit-events")
def list_access_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """Read append-only authorization events without leaking other departments' history."""

    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    scoped_events = (
        select(AuthorizationAuditEvent, Department.code.label("department_code"))
        .outerjoin(Department, Department.id == AuthorizationAuditEvent.department_id)
        .where(
            or_(
                Department.code.in_(allowed_departments),
                AuthorizationAuditEvent.actor_auth_user_id == principal.user_id,
            )
        )
        .order_by(AuthorizationAuditEvent.created_at.desc(), AuthorizationAuditEvent.id.desc())
    )
    total = db.scalar(select(func.count()).select_from(scoped_events.subquery())) or 0
    rows = db.execute(scoped_events.limit(limit).offset(offset)).all()
    return {
        "total": total,
        "items": [
            _authorization_audit_event_to_dict(event, department_code)
            for event, department_code in rows
        ],
    }


@app.post("/api/followup-agent/creators", status_code=201)
def create_creator(
    body: CreatorCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    _require_department_capability(principal, Capability.CREATOR_MANAGE, body.department_code)
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    creator = _scoped_creator_or_404(db, creator_id, principal, Capability.CREATOR_MANAGE)
    _require_department_capability(principal, Capability.CREATOR_MANAGE, body.department_code)
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    creator = _scoped_creator_or_404(db, creator_id, principal, Capability.CREATOR_MANAGE)
    if body.department_code is not None:
        _require_department_capability(principal, Capability.CREATOR_MANAGE, body.department_code)
    # exclude_unset 能区分“字段未提供”和“调用方显式传 null”。
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(creator, key, value)
    db.commit()
    db.refresh(creator)
    return {"ok": True, "creator": _creator_to_dict(creator)}


@app.post("/api/followup-agent/products", status_code=201)
def create_product(
    body: ProductCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    ensure_capability(principal, Capability.CATALOG_MANAGE)
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    ensure_capability(principal, Capability.CATALOG_MANAGE)
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    ensure_capability(principal, Capability.CATALOG_MANAGE)
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
def create_reference_material(
    body: ReferenceMaterialCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """创建首个参考资料版本，并将同一资料键的旧活动版本停用。"""

    ensure_capability(principal, Capability.CATALOG_MANAGE)
    version = int(db.scalar(select(func.max(ReferenceMaterial.version)).where(ReferenceMaterial.reference_key == body.reference_key)) or 0) + 1
    db.query(ReferenceMaterial).filter(ReferenceMaterial.reference_key == body.reference_key).update({"is_active": False})
    row = ReferenceMaterial(id=new_id("ref"), version=version, is_active=True, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "reference_material": _reference_material_to_dict(row)}


@app.patch("/api/followup-agent/reference-materials/{reference_key}")
def version_reference_material(
    reference_key: str,
    body: ReferenceMaterialVersionIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """以新增版本替代当前活动资料，保留旧版本供历史 run 追溯。"""

    ensure_capability(principal, Capability.CATALOG_MANAGE)
    exists = db.scalar(select(ReferenceMaterial.id).where(ReferenceMaterial.reference_key == reference_key).limit(1))
    if exists is None:
        raise HTTPException(status_code=404, detail="reference material not found")
    version = int(db.scalar(select(func.max(ReferenceMaterial.version)).where(ReferenceMaterial.reference_key == reference_key)) or 0) + 1
    db.query(ReferenceMaterial).filter(ReferenceMaterial.reference_key == reference_key).update({"is_active": False})
    row = ReferenceMaterial(id=new_id("ref"), reference_key=reference_key, version=version, is_active=True, **body.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"ok": True, "reference_material": _reference_material_to_dict(row)}


@app.get("/api/followup-agent/reference-materials")
def list_reference_materials(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """按版本列出参考资料，可选择只查看当前启用版本。"""

    # Reference materials are global configuration, but still never public.
    # Resolving the principal here keeps them available to every active role.
    del principal
    query = select(ReferenceMaterial)
    if active_only:
        query = query.where(ReferenceMaterial.is_active.is_(True))
    rows = list(db.scalars(query.order_by(ReferenceMaterial.reference_key.asc(), ReferenceMaterial.version.desc())).all())
    return {"ok": True, "items": [_reference_material_to_dict(row) for row in rows]}


@app.get("/api/followup-agent/outbound-instructions")
def list_outbound_instructions(
    creator_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """查询内部模拟出站指令，当前接口不会触发任何外部渠道发送。"""

    allowed_departments = _allowed_departments(principal, Capability.OUTBOUND_READ)
    query = (
        select(SimulatedOutboundInstruction)
        .join(Creator, Creator.id == SimulatedOutboundInstruction.creator_id)
        .where(Creator.department_code.in_(allowed_departments))
    )
    if creator_id:
        query = query.where(SimulatedOutboundInstruction.creator_id == creator_id)
    rows = list(db.scalars(query.order_by(SimulatedOutboundInstruction.created_at.desc())).all())
    return {"ok": True, "total": len(rows), "items": [{"id": row.id, "creator_id": row.creator_id, "inbound_reply_id": row.inbound_reply_id, "action_type": row.action_type, "template_key": row.template_key, "content": row.content, "status": row.status} for row in rows]}


@app.post("/api/followup-agent/simulate-reply")
def simulate_reply(
    body: SimulateReplyIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    creator = _scoped_creator_or_404(db, body.creator_id, principal, Capability.SIMULATION_WRITE)
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
def run_agent(
    body: RunAgentIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    allowed_departments = _allowed_departments(principal, Capability.RUN_ENQUEUE)
    reply = db.scalar(
        select(InboundReply).where(
            InboundReply.id == body.inbound_reply_id,
            InboundReply.department_code.in_(allowed_departments),
        )
    )
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
    run = _create_run(db, body.inbound_reply_id, created_by=principal.user_id)
    db.commit()
    return {"ok": True, "run": _run_to_dict(run)}


@app.get("/api/followup-agent/replies/{reply_id}")
def get_reply(
    reply_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    reply = db.scalar(
        select(InboundReply).where(
            InboundReply.id == reply_id,
            InboundReply.department_code.in_(allowed_departments),
        )
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    return {"ok": True, "reply": _reply_to_dict(reply)}


@app.get("/api/followup-agent/runs/{run_id}")
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    run = db.scalar(
        select(AgentFollowupRun).where(
            AgentFollowupRun.id == run_id,
            AgentFollowupRun.department_code.in_(allowed_departments),
        )
    )
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    filters = [AgentFollowupRun.department_code.in_(allowed_departments)]
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
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """列出工作台中的待审、生成中与已批准草稿项。"""

    allowed_review_types = {
        "standard",
        "model_failure",
        "decline",
        "dnc_confirmation",
        "generation_pending",
        "approved_draft",
        "reply_ready",
    }
    if review_type is not None and review_type not in allowed_review_types:
        raise HTTPException(status_code=422, detail="unknown review_type")
    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    scoped_departments: Collection[str]
    if department_code is not None and department_code not in allowed_departments:
        # A list endpoint never confirms that another department exists.
        scoped_departments = ()
    elif department_code is not None:
        scoped_departments = (department_code,)
    else:
        scoped_departments = allowed_departments
    statement, review_type_expression = _review_queue_base_statement(scoped_departments)
    filtered_statement = _apply_review_queue_filters(
        statement,
        review_type_expression,
        review_type=review_type,
        include_dnc_blocked=False,
    )
    total = int(db.scalar(select(func.count()).select_from(filtered_statement.subquery())) or 0)
    rows = db.execute(
        filtered_statement.order_by(InboundReply.created_at.desc(), InboundReply.id.desc()).offset(offset).limit(limit)
    ).all()
    return {"ok": True, "total": total, "items": [_review_queue_item_from_row(row) for row in rows]}


@app.get("/api/followup-agent/review-items/{reply_id}")
def get_human_review_item(
    reply_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """读取工作台项的当前上下文与完整 Agent run 留痕，不写入业务数据。"""

    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    reply = db.scalar(
        select(InboundReply).where(
            InboundReply.id == reply_id,
            InboundReply.department_code.in_(allowed_departments),
        )
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    item = _load_review_queue_item(
        db,
        reply_id,
        include_dnc_blocked=True,
        department_codes=allowed_departments,
    )
    if item is None:
        raise HTTPException(status_code=409, detail="reply is not available in the operator workbench")
    runs = list(
        db.scalars(
            select(AgentFollowupRun)
            .where(AgentFollowupRun.inbound_reply_id == reply.id)
            .order_by(AgentFollowupRun.created_at.asc(), AgentFollowupRun.id.asc())
        ).all()
    )
    # DNC is a conservative terminal boundary.  Keep run metadata available for
    # audit, but never expose a prior AI draft once the creator has requested or
    # confirmed do-not-contact.
    dnc_blocked = item["review_type"] in {"dnc_confirmation", "dnc_blocked"}
    return {
        "ok": True,
        "item": item,
        "context": build_followup_context(db, reply.id),
        "runs": [_run_to_dnc_safe_dict(run) if dnc_blocked else _run_to_dict(run) for run in runs],
    }


@app.post("/api/followup-agent/dnc-confirmations/{confirmation_id}/approve")
def approve_dnc_confirmation(
    confirmation_id: str,
    body: DncConfirmationApproveIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """人工确认待审 DNC，并永久阻断该达人后续业务联系；不发送任何消息。"""

    allowed_departments = _allowed_departments(principal, Capability.DNC_DECIDE)
    confirmation = db.scalars(
        select(DoNotContactConfirmation)
        .join(Creator, Creator.id == DoNotContactConfirmation.creator_id)
        .where(
            DoNotContactConfirmation.id == confirmation_id,
            Creator.department_code.in_(allowed_departments),
        )
        .with_for_update()
    ).first()
    if confirmation is None:
        raise HTTPException(status_code=404, detail="do not contact confirmation not found")
    if confirmation.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="do not contact confirmation is not pending")

    creator = db.get(Creator, confirmation.creator_id)
    reply = db.get(InboundReply, confirmation.inbound_reply_id)
    if creator is None or reply is None:
        raise HTTPException(status_code=409, detail="do not contact confirmation has incomplete audit references")
    if reply.processing_status != "need_ai_review":
        raise HTTPException(status_code=409, detail="reply is not pending human review")

    reviewed_at = datetime.utcnow()
    confirmation.status = "confirmed"
    confirmation.reviewed_by = principal.user_id
    confirmation.reviewed_at = reviewed_at
    creator.do_not_contact_status = "confirmed"
    creator.do_not_contact_reason = confirmation.reason
    creator.do_not_contact_requested_at = creator.do_not_contact_requested_at or confirmation.created_at or reviewed_at
    reply.processing_status = "reviewed"
    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="dnc_confirmed_by_human",
            note="Do-not-contact request was confirmed by a human reviewer; no outbound message was sent.",
            metadata_json=json.dumps(
                {
                    "actor_id": principal.user_id,
                    "dnc_confirmation_id": confirmation.id,
                    "inbound_reply_id": reply.id,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    db.refresh(confirmation)
    db.refresh(creator)
    db.refresh(reply)
    return {
        "ok": True,
        "confirmation": _dnc_confirmation_to_dict(confirmation),
        "creator": _creator_to_dict(creator),
        "reply": _reply_to_dict(reply),
    }


@app.post("/api/followup-agent/dnc-confirmations/{confirmation_id}/reject")
def reject_dnc_confirmation(
    confirmation_id: str,
    body: DncConfirmationRejectIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """人工驳回 DNC 判定，将该回复重新入队为普通审核；不发送任何消息。"""

    allowed_departments = _allowed_departments(principal, Capability.DNC_DECIDE)
    confirmation = db.scalars(
        select(DoNotContactConfirmation)
        .join(Creator, Creator.id == DoNotContactConfirmation.creator_id)
        .where(
            DoNotContactConfirmation.id == confirmation_id,
            Creator.department_code.in_(allowed_departments),
        )
        .with_for_update()
    ).first()
    if confirmation is None:
        raise HTTPException(status_code=404, detail="do not contact confirmation not found")
    if confirmation.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail="do not contact confirmation is not pending")

    creator = db.get(Creator, confirmation.creator_id)
    reply = db.get(InboundReply, confirmation.inbound_reply_id)
    if creator is None or reply is None:
        raise HTTPException(status_code=409, detail="do not contact confirmation has incomplete audit references")
    if reply.processing_status != "need_ai_review":
        raise HTTPException(status_code=409, detail="reply is not pending human review")

    original_category = reply.reply_category
    original_reason = reply.classification_reason
    reviewed_at = datetime.utcnow()
    confirmation.status = "rejected"
    confirmation.reviewed_by = principal.user_id
    confirmation.reviewed_at = reviewed_at
    creator.do_not_contact_status = "none"
    creator.do_not_contact_reason = None
    creator.do_not_contact_requested_at = None
    # 保留原始规则命中在 DNC 流水和事件元数据中；当前回复改由人工触发的普通审核重新处理。
    reply.reply_category = "unclear"
    reply.classification_confidence = None
    reply.classification_reason = "human_rejected_dnc_confirmation"
    reply.classified_at = reviewed_at

    blocked_tasks = list(
        db.scalars(
            select(FollowupTask)
            .where(FollowupTask.creator_id == creator.id)
            .where(FollowupTask.status == "blocked_dnc_pending")
        ).all()
    )
    for task in blocked_tasks:
        task.status = "blocked_dnc_rejected"
        task.reason = "DNC was rejected by a human reviewer; manually reassess before resuming any follow-up."

    run = enqueue_followup_run(db, reply.id, created_by=principal.user_id)
    db.add(
        CreatorOutreachEvent(
            id=new_id("oev"),
            department_code=creator.department_code,
            creator_id=creator.id,
            event_type="dnc_rejected_by_human",
            note="Do-not-contact classification was rejected by a human reviewer; a new review run was queued without sending a message.",
            metadata_json=json.dumps(
                {
                    "actor_id": principal.user_id,
                    "dnc_confirmation_id": confirmation.id,
                    "inbound_reply_id": reply.id,
                    "original_reply_category": original_category,
                    "original_classification_reason": original_reason,
                    "queued_run_id": run.id,
                },
                ensure_ascii=False,
            ),
        )
    )
    db.commit()
    db.refresh(confirmation)
    db.refresh(creator)
    db.refresh(reply)
    db.refresh(run)
    return {
        "ok": True,
        "confirmation": _dnc_confirmation_to_dict(confirmation),
        "creator": _creator_to_dict(creator),
        "reply": _reply_to_dict(reply),
        "run": _run_to_dict(run),
    }


@app.post("/api/followup-agent/review-items/{reply_id}/retry")
def retry_failed_human_review_item(
    reply_id: str,
    body: FailedReviewRetryIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """人工重试最新模型失败的待审项；只创建新的 queued run，不发送任何消息。"""

    allowed_departments = _allowed_departments(principal, Capability.RUN_RETRY)
    reply = db.scalar(
        select(InboundReply).where(
            InboundReply.id == reply_id,
            InboundReply.department_code.in_(allowed_departments),
        )
    )
    if reply is None:
        raise HTTPException(status_code=404, detail="inbound reply not found")
    if reply.processing_status != "need_ai_review":
        raise HTTPException(status_code=409, detail="reply is not pending human review")

    item = _load_review_queue_item(
        db,
        reply.id,
        include_dnc_blocked=True,
        department_codes=allowed_departments,
    )
    if item is None:
        raise HTTPException(status_code=409, detail="reply is not available in the operator workbench")
    if item["review_type"] != "model_failure" or item["run"] is None:
        raise HTTPException(status_code=409, detail="only a model-failure review item can be retried")
    active_run = db.scalar(
        select(AgentFollowupRun.id)
        .where(AgentFollowupRun.inbound_reply_id == reply.id)
        .where(AgentFollowupRun.execution_status.in_(("queued", "running")))
        .limit(1)
    )
    if active_run is not None:
        raise HTTPException(status_code=409, detail="agent retry is already queued")

    try:
        run = enqueue_followup_run(
            db,
            reply.id,
            created_by=principal.user_id,
            reject_if_active=True,
        )
    except IntegrityError:
        # The active-run unique index is the final arbiter under concurrent
        # requests; expose its conflict as the same business result as the
        # pre-check rather than leaking a database error as HTTP 500.
        db.rollback()
        raise HTTPException(status_code=409, detail="agent retry is already queued")

    creator = db.get(Creator, reply.creator_id)
    if creator is not None:
        db.add(
            CreatorOutreachEvent(
                id=new_id("oev"),
                department_code=creator.department_code,
                creator_id=creator.id,
                event_type="agent_retry_requested_by_human",
                note="A human reviewer requested another draft generation after a model failure; no outbound message was sent.",
                metadata_json=json.dumps(
                    {
                        "actor_id": principal.user_id,
                        "inbound_reply_id": reply.id,
                        "failed_run_id": item["run"]["id"],
                        "queued_run_id": run.id,
                    },
                    ensure_ascii=False,
                ),
            )
        )
    db.commit()
    db.refresh(run)
    return {"ok": True, "run": _run_to_dict(run), "reply": _reply_to_dict(reply)}


@app.post("/api/followup-agent/review-decisions", status_code=201)
def create_human_review_decision(
    body: HumanReviewDecisionCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """保存普通回复的最终人工决定，不自动推进达人业务状态。"""

    allowed_departments = _allowed_departments(principal, Capability.REVIEW_DECIDE)
    run = db.scalar(
        select(AgentFollowupRun).where(
            AgentFollowupRun.id == body.agent_followup_run_id,
            AgentFollowupRun.department_code.in_(allowed_departments),
        )
    )
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

    decision = HumanReviewDecision(
        id=new_id("hrd"),
        department_code=reply.department_code,
        creator_id=reply.creator_id,
        inbound_reply_id=reply.id,
        agent_followup_run_id=run.id,
        outcome=body.outcome,
        final_draft=body.final_draft.strip() if body.final_draft is not None else None,
        note=body.note,
        actor_id=principal.user_id,
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
def get_human_review_decision(
    decision_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """读取不可变审核决定及其导出审计，不触发复制、导出或发送。"""

    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    decision = db.scalar(
        select(HumanReviewDecision).where(
            HumanReviewDecision.id == decision_id,
            HumanReviewDecision.department_code.in_(allowed_departments),
        )
    )
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


@app.get("/api/followup-agent/review-decisions/{decision_id}/delivery-capability")
def get_draft_delivery_capability(
    decision_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """返回未来渠道交接的能力边界；该预留接口不发送也不写入任何数据。"""

    allowed_departments = _allowed_departments(principal, Capability.REVIEW_READ)
    decision = db.scalar(
        select(HumanReviewDecision).where(
            HumanReviewDecision.id == decision_id,
            HumanReviewDecision.department_code.in_(allowed_departments),
        )
    )
    if decision is None:
        raise HTTPException(status_code=404, detail="human review decision not found")
    if decision.outcome != "approve_draft" or not decision.final_draft:
        raise HTTPException(status_code=409, detail="human review decision has no approved draft")

    creator = db.get(Creator, decision.creator_id)
    if is_creator_contact_blocked(creator):
        return {
            "ok": True,
            "delivery_available": False,
            "delivery_status": "not_sent_by_system",
            "delivery_mode": "blocked_by_do_not_contact",
            "reason": "do not contact creator cannot receive a draft handoff",
        }
    return {
        "ok": True,
        "delivery_available": False,
        "delivery_status": "not_sent_by_system",
        "delivery_mode": "manual_copy_or_export_only",
        "reason": "external delivery channels are not configured",
    }


@app.post("/api/followup-agent/review-decisions/{decision_id}/exports", status_code=201)
def create_draft_export_record(
    decision_id: str,
    body: DraftExportCreateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, Any]:
    """记录人工导出草稿的快照；该接口绝不调用外部渠道。"""

    allowed_departments = _allowed_departments(principal, Capability.DRAFT_EXPORT)
    decision = db.scalar(
        select(HumanReviewDecision).where(
            HumanReviewDecision.id == decision_id,
            HumanReviewDecision.department_code.in_(allowed_departments),
        )
    )
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
        actor_id=principal.user_id,
    )
    db.add(export)
    db.commit()
    db.refresh(export)
    return {"ok": True, "export": _draft_export_record_to_dict(export)}


def _create_run(db: Session, inbound_reply_id: str, *, created_by: str) -> AgentFollowupRun:
    return enqueue_followup_run(db, inbound_reply_id, created_by=created_by)


def _allowed_departments(principal: Principal, capability: Capability) -> frozenset[str]:
    """Return only departments where this principal has the requested ability."""

    ensure_capability(principal, capability)
    return principal.allowed_departments_for(capability)


def _normalise_department_code(value: str) -> str:
    code = value.strip().lower()
    if not code:
        raise HTTPException(status_code=422, detail="department code must not be empty")
    return code


def _current_auth_user_or_503(db: Session, principal: Principal) -> AuthUser:
    """Defend against a concurrent local revocation after identity resolution."""

    user = db.get(AuthUser, principal.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=503, detail="current authorization mapping is unavailable")
    return user


def _managed_department_or_404(db: Session, department_code: str, principal: Principal) -> Department:
    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    department = db.scalar(
        select(Department).where(
            Department.code == _normalise_department_code(department_code),
            Department.code.in_(allowed_departments),
        )
    )
    if department is None:
        raise HTTPException(status_code=404, detail="department not found")
    return department


def _managed_auth_user_or_404(
    db: Session,
    auth_user_id: str,
    principal: Principal,
    *,
    allow_unassigned: bool = False,
) -> AuthUser:
    """Return a user only when every existing department relationship is manageable."""

    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    user = db.get(AuthUser, auth_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="auth user not found")
    membership_departments = db.scalars(
        select(Department.code)
        .join(UserDepartmentMembership, UserDepartmentMembership.department_id == Department.id)
        .where(UserDepartmentMembership.auth_user_id == user.id)
    ).all()
    if any(code not in allowed_departments for code in membership_departments):
        raise HTTPException(status_code=404, detail="auth user not found")
    if not membership_departments and not allow_unassigned:
        raise HTTPException(status_code=404, detail="auth user not found")
    return user


def _managed_membership_or_404(
    db: Session,
    membership_id: str,
    principal: Principal,
) -> tuple[UserDepartmentMembership, Department]:
    allowed_departments = _allowed_departments(principal, Capability.ACCESS_MANAGE)
    row = db.execute(
        select(UserDepartmentMembership, Department)
        .join(Department, Department.id == UserDepartmentMembership.department_id)
        .where(
            UserDepartmentMembership.id == membership_id,
            Department.code.in_(allowed_departments),
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="department membership not found")
    return row


def _append_authorization_audit(
    db: Session,
    *,
    action: str,
    actor_auth_user_id: str | None,
    target_auth_user_id: str | None = None,
    department_id: str | None = None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> AuthorizationAuditEvent:
    """Append a change record; this module never updates or deletes audit rows."""

    event = AuthorizationAuditEvent(
        id=new_id("auth_audit"),
        action=action,
        actor_auth_user_id=actor_auth_user_id,
        target_auth_user_id=target_auth_user_id,
        department_id=department_id,
        before_json=json.dumps(before, ensure_ascii=False, sort_keys=True) if before is not None else None,
        after_json=json.dumps(after, ensure_ascii=False, sort_keys=True) if after is not None else None,
    )
    db.add(event)
    return event


def _require_department_capability(
    principal: Principal,
    capability: Capability,
    department_code: str,
) -> None:
    """Require a write capability in one explicit target department."""

    ensure_capability(principal, capability, department_code=department_code)


def _scoped_creator_or_404(
    db: Session,
    creator_id: str,
    principal: Principal,
    capability: Capability,
) -> Creator:
    """Load a creator only from a department manageable by this principal."""

    allowed_departments = _allowed_departments(principal, capability)
    creator = db.scalar(
        select(Creator).where(
            Creator.id == creator_id,
            Creator.department_code.in_(allowed_departments),
        )
    )
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    return creator


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


def _review_queue_base_statement(department_codes: str | Collection[str] | None):
    """Build the shared, set-based read model for queue items and details."""

    if isinstance(department_codes, str):
        scoped_departments: tuple[str, ...] | None = (department_codes,)
    elif department_codes is None:
        scoped_departments = None
    else:
        scoped_departments = tuple(department_codes)

    pending_candidates = select(InboundReply.id.label("reply_id")).where(
        InboundReply.processing_status == "need_ai_review"
    )
    approved_candidates = (
        select(HumanReviewDecision.inbound_reply_id.label("reply_id"))
        .join(InboundReply, InboundReply.id == HumanReviewDecision.inbound_reply_id)
        .where(HumanReviewDecision.outcome == "approve_draft")
    )
    if scoped_departments is not None:
        pending_candidates = pending_candidates.where(InboundReply.department_code.in_(scoped_departments))
        approved_candidates = approved_candidates.where(InboundReply.department_code.in_(scoped_departments))

    candidate_reply_ids = union(pending_candidates, approved_candidates).cte("review_candidate_reply_ids")
    ranked_runs = (
        select(
            AgentFollowupRun.id.label("run_id"),
            AgentFollowupRun.inbound_reply_id.label("reply_id"),
            func.row_number()
            .over(
                partition_by=AgentFollowupRun.inbound_reply_id,
                order_by=(AgentFollowupRun.created_at.desc(), AgentFollowupRun.id.desc()),
            )
            .label("rank"),
        )
        .join(candidate_reply_ids, candidate_reply_ids.c.reply_id == AgentFollowupRun.inbound_reply_id)
        .cte("review_ranked_runs")
    )
    latest_run_ids = (
        select(ranked_runs.c.reply_id, ranked_runs.c.run_id)
        .where(ranked_runs.c.rank == 1)
        .cte("review_latest_run_ids")
    )
    candidate_creator_ids = (
        select(InboundReply.creator_id.label("creator_id"))
        .join(candidate_reply_ids, candidate_reply_ids.c.reply_id == InboundReply.id)
        .distinct()
        .cte("review_candidate_creator_ids")
    )
    ranked_dnc_confirmations = (
        select(
            DoNotContactConfirmation.id.label("confirmation_id"),
            DoNotContactConfirmation.creator_id.label("creator_id"),
            func.row_number()
            .over(
                partition_by=DoNotContactConfirmation.creator_id,
                order_by=(DoNotContactConfirmation.created_at.desc(), DoNotContactConfirmation.id.desc()),
            )
            .label("rank"),
        )
        .join(
            candidate_creator_ids,
            candidate_creator_ids.c.creator_id == DoNotContactConfirmation.creator_id,
        )
        .where(DoNotContactConfirmation.status.in_(("pending_confirmation", "confirmed")))
        .cte("review_ranked_dnc_confirmations")
    )
    latest_dnc_ids = (
        select(ranked_dnc_confirmations.c.creator_id, ranked_dnc_confirmations.c.confirmation_id)
        .where(ranked_dnc_confirmations.c.rank == 1)
        .cte("review_latest_dnc_ids")
    )

    latest_run = aliased(AgentFollowupRun)
    latest_dnc_confirmation = aliased(DoNotContactConfirmation)
    creator_is_dnc_blocked = Creator.do_not_contact_status.in_(("pending_confirmation", "confirmed"))
    review_type_expression = case(
        (
            and_(
                creator_is_dnc_blocked,
                latest_dnc_confirmation.inbound_reply_id == InboundReply.id,
            ),
            "dnc_confirmation",
        ),
        (creator_is_dnc_blocked, "dnc_blocked"),
        (HumanReviewDecision.outcome == "approve_draft", "approved_draft"),
        (InboundReply.reply_category == "not_interested", "decline"),
        (latest_run.execution_status.in_(("queued", "running")), "generation_pending"),
        (latest_run.execution_status == "failed", "model_failure"),
        else_="standard",
    )
    statement = (
        select(
            InboundReply,
            Creator,
            latest_run,
            latest_dnc_confirmation,
            HumanReviewDecision,
            review_type_expression.label("review_type"),
        )
        .join(candidate_reply_ids, candidate_reply_ids.c.reply_id == InboundReply.id)
        .join(Creator, Creator.id == InboundReply.creator_id)
        .outerjoin(latest_run_ids, latest_run_ids.c.reply_id == InboundReply.id)
        .outerjoin(latest_run, latest_run.id == latest_run_ids.c.run_id)
        .outerjoin(latest_dnc_ids, latest_dnc_ids.c.creator_id == InboundReply.creator_id)
        .outerjoin(latest_dnc_confirmation, latest_dnc_confirmation.id == latest_dnc_ids.c.confirmation_id)
        .outerjoin(HumanReviewDecision, HumanReviewDecision.inbound_reply_id == InboundReply.id)
    )
    return statement, review_type_expression


def _apply_review_queue_filters(
    statement,
    review_type_expression,
    *,
    review_type: str | None,
    include_dnc_blocked: bool,
):
    """Apply queue visibility and API filters before counting or paging."""

    if not include_dnc_blocked:
        statement = statement.where(review_type_expression != "dnc_blocked")
    if review_type == "reply_ready":
        return statement.where(review_type_expression.in_(("standard", "approved_draft")))
    if review_type is not None:
        return statement.where(review_type_expression == review_type)
    return statement


def _load_review_queue_item(
    db: Session,
    reply_id: str,
    *,
    include_dnc_blocked: bool,
    department_codes: Collection[str] | None = None,
) -> dict[str, Any] | None:
    """Load one candidate through the same SQL read model as the queue."""

    statement, review_type_expression = _review_queue_base_statement(department_codes=department_codes)
    row = db.execute(
        _apply_review_queue_filters(
            statement.where(InboundReply.id == reply_id),
            review_type_expression,
            review_type=None,
            include_dnc_blocked=include_dnc_blocked,
        )
    ).one_or_none()
    return _review_queue_item_from_row(row) if row is not None else None


def _review_queue_item_from_row(row) -> dict[str, Any]:
    """Serialize a queue row without issuing any per-item database queries."""

    reply, _creator, latest_run, dnc_confirmation, decision, review_type = row
    decision_available = (
        review_type in {"standard", "model_failure"}
        and latest_run is not None
        and latest_run.execution_status in {"succeeded", "failed"}
    )
    dnc_blocked = review_type in {"dnc_confirmation", "dnc_blocked"}
    run_payload = _run_to_dict(latest_run) if latest_run is not None else None
    decision_payload = _human_review_decision_to_dict(decision) if decision is not None else None
    if dnc_blocked:
        run_payload = _run_to_dnc_safe_dict(latest_run) if latest_run is not None else None
        decision_payload = None
    return {
        "review_type": review_type,
        "decision_available": decision_available,
        "reply": _reply_to_dict(reply),
        "run": run_payload,
        "dnc_confirmation": _dnc_confirmation_to_dict(dnc_confirmation)
        if review_type == "dnc_confirmation" and dnc_confirmation
        else None,
        "decision": decision_payload,
    }


def _run_to_dnc_safe_dict(row: AgentFollowupRun) -> dict[str, Any]:
    """Return audit metadata without any AI draft for a DNC-blocked creator."""

    payload = _run_to_dict(row)
    payload["output"] = None
    return payload


def _auth_user_snapshot(row: AuthUser) -> dict[str, object]:
    return {
        "id": row.id,
        "identity_source": row.identity_source,
        "external_subject": row.external_subject,
        "display_name": row.display_name,
        "is_active": bool(row.is_active),
    }


def _auth_user_to_dict(row: AuthUser) -> dict[str, object]:
    return {
        **_auth_user_snapshot(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _department_snapshot(row: Department) -> dict[str, object]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "is_active": bool(row.is_active),
    }


def _department_to_dict(row: Department) -> dict[str, object]:
    return {
        **_department_snapshot(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _membership_snapshot(
    row: UserDepartmentMembership,
    department_code: str,
) -> dict[str, object]:
    return {
        "id": row.id,
        "auth_user_id": row.auth_user_id,
        "department_code": department_code,
        "role": row.role,
        "is_active": bool(row.is_active),
        "authorization_source": row.authorization_source,
        "granted_by_auth_user_id": row.granted_by_auth_user_id,
    }


def _membership_to_dict(
    row: UserDepartmentMembership,
    department: Department,
) -> dict[str, object]:
    return {
        **_membership_snapshot(row, department.code),
        "department_name": department.name,
        "department_is_active": bool(department.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _authorization_audit_event_to_dict(
    row: AuthorizationAuditEvent,
    department_code: str | None,
) -> dict[str, object]:
    return {
        "id": row.id,
        "action": row.action,
        "actor_auth_user_id": row.actor_auth_user_id,
        "target_auth_user_id": row.target_auth_user_id,
        "department_code": department_code,
        "before": _load_json(row.before_json),
        "after": _load_json(row.after_json),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


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
        "department_code": row.department_code,
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
        "created_by": row.created_by,
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
