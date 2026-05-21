from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.creator import Creator
from ..models.creator_source import CreatorSource
from ..services.departments import current_user, row_in_department
from ..services.post_processing import create_outreach_event, recommendation_visibility


router = APIRouter(prefix="/api/local/recommendations", tags=["recommendations"])

RECOMMENDABLE_STATUSES = {
    "recommended",
    "recommended_after_review",
    "low_cost_test",
    "affiliate_test",
    "brand_awareness_only",
}


class AssignIn(BaseModel):
    owner_bd: str | None = None
    force: bool = False
    note: str | None = None


def _owner_label(user: dict, override: str | None = None) -> str:
    if override:
        return override.strip()
    return str(user.get("display_name") or user.get("username") or user.get("email") or user.get("id") or "").strip()


def _actor_id(user: dict) -> str:
    return str(user.get("id") or user.get("identity") or user.get("username") or "")


def _source_types(db: Session, creator_id: str) -> list[str]:
    rows = db.scalars(select(CreatorSource.source_type).where(CreatorSource.creator_id == creator_id)).all()
    return sorted({str(row) for row in rows if row})


def _creator_payload(db: Session, creator: Creator) -> dict[str, Any]:
    visibility = recommendation_visibility(db, creator)
    return {
        "id": creator.id,
        "platform": creator.platform,
        "handle": creator.handle,
        "display_name": creator.display_name,
        "department_code": creator.department_code,
        "source_types": _source_types(db, creator.id),
        "owner_bd": creator.owner_bd,
        "current_status": creator.current_status,
        "recommendation_status": creator.recommendation_status,
        "recommended_product_type": creator.recommended_product_type,
        "recommended_collab_type": creator.recommended_collab_type,
        "outreach_priority": creator.outreach_priority,
        "recommendation_score": creator.recommendation_score,
        "recommendation_reason": creator.recommendation_reason,
        "next_action": creator.next_action,
        **visibility,
    }


@router.get("")
def list_recommendations(
    request: Request,
    source_type: str | None = None,
    department_code: str | None = None,
    availability: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    current_user(request)
    q = select(Creator).where(Creator.recommendation_status.in_(RECOMMENDABLE_STATUSES))
    if department_code:
        q = q.where(Creator.department_code == department_code)
    if source_type:
        q = q.join(CreatorSource, CreatorSource.creator_id == Creator.id).where(CreatorSource.source_type == source_type)
    q = q.distinct()
    rows = list(
        db.scalars(
            q.order_by(Creator.recommendation_score.desc(), Creator.updated_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    items = [_creator_payload(db, row) for row in rows]
    if availability:
        items = [item for item in items if item.get("availability") == availability]
    return {"ok": True, "total": len(items), "limit": limit, "offset": offset, "items": items}


@router.post("/{creator_id}/assign")
def assign_recommendation(creator_id: str, body: AssignIn, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request)
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail="creator not found")
    # Recommendation pool is readable platform-wide; write operations still
    # respect department ownership unless the actor is company/super admin.
    if user.get("role") not in {"company_admin", "super_admin"} and not row_in_department(creator, user.get("department_code")):
        raise HTTPException(status_code=404, detail="creator not found")
    owner = _owner_label(user, body.owner_bd)
    if not owner:
        raise HTTPException(status_code=400, detail="owner is required")
    current_owner = (creator.owner_bd or "").strip()
    is_admin = user.get("role") in {"department_admin", "company_admin", "super_admin"}
    if current_owner and current_owner.lower() != owner.lower() and not (body.force and is_admin):
        raise HTTPException(status_code=409, detail=f"creator already assigned to {current_owner}")
    create_outreach_event(
        db,
        creator,
        event_type="assigned",
        actor_user_id=_actor_id(user),
        owner_bd=owner,
        note=body.note,
        metadata={"source": "recommendation_assign"},
    )
    db.commit()
    db.refresh(creator)
    return {"ok": True, "item": _creator_payload(db, creator)}
