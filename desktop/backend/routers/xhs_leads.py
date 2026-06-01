"""Xiaohongshu / Douyin social-lead API (Phase 3): snapshot ingest, GPT
purchase-intent judge, and a department-scoped user list for the social-leads
page. The browser extension POSTs collection snapshots to the ingest endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.social_lead import XhsAiJudgment, XhsExtractedContact, XhsUser
from ..services.departments import current_department_code, department_where
from ..services.xhs_lead_service import ingest_snapshot, judge_users_with_gpt

router = APIRouter(prefix="/api/local/xhs", tags=["xhs-leads"])


@router.post("/ingest")
def xhs_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_snapshot(db, payload, platform="xhs", department_code=current_department_code(request))


@router.post("/douyin/ingest")
def douyin_ingest(request: Request, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> dict[str, Any]:
    return ingest_snapshot(db, payload, platform="douyin", department_code=current_department_code(request))


@router.post("/judge")
def judge(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return judge_users_with_gpt(db, department_code=current_department_code(request), limit=limit, force=force)


@router.get("/users")
def list_users(
    request: Request,
    platform: str | None = Query(default=None),
    has_contact: int | None = Query(default=None),
    decision: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    department_code = current_department_code(request)
    base = select(XhsUser)
    where = department_where(XhsUser, department_code)
    if where is not None:
        base = base.where(where)
    if platform:
        base = base.where(XhsUser.platform == platform)
    if has_contact is not None:
        base = base.where(XhsUser.has_contact == has_contact)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(XhsUser.username_clean.ilike(like), XhsUser.bio_clean.ilike(like), XhsUser.location_text.ilike(like)))

    total = int(db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0)
    users = list(db.scalars(base.order_by(XhsUser.created_at.desc()).limit(limit).offset(offset)).all())

    # latest judgment per user (small page → per-user lookup is fine)
    judgments: dict[str, XhsAiJudgment] = {}
    contact_counts: dict[str, int] = {}
    for u in users:
        j = db.scalar(select(XhsAiJudgment).where(XhsAiJudgment.user_id == u.id).order_by(XhsAiJudgment.created_at.desc()))
        if j is not None:
            judgments[u.id] = j
        contact_counts[u.id] = int(db.scalar(select(func.count()).select_from(XhsExtractedContact).where(XhsExtractedContact.user_id == u.id)) or 0)

    if decision:
        users = [u for u in users if (judgments.get(u.id) and judgments[u.id].decision == decision)]

    items = []
    for u in users:
        j = judgments.get(u.id)
        items.append({
            "id": u.id,
            "platform": u.platform,
            "username": u.username_clean or u.account_clean or u.xhs_user_id,
            "bio": u.bio_clean,
            "location": u.location_text,
            "follower_count": u.follower_count,
            "has_contact": int(u.has_contact or 0),
            "contact_count": contact_counts.get(u.id, 0),
            "profile_url": u.canonical_profile_url,
            "fit_score": j.fit_score if j else None,
            "fit_level": j.fit_level if j else None,
            "decision": j.decision if j else None,
            "intent_type": j.intent_type if j else None,
            "created_at": u.created_at.isoformat() if hasattr(u.created_at, "isoformat") else u.created_at,
        })
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}
