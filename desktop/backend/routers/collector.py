from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.raw_observation import RawObservation
from ..services.collector_service import ingest_observation
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, department_where


router = APIRouter(prefix="/api/local/collector", tags=["collector"])


def _iso_or_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


@router.post("/observations")
def post_observation(payload: dict[str, Any], request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        if getattr(request.state, "current_user", None):
            payload.setdefault("department_code", current_department_code(request))
        else:
            payload.setdefault("department_code", DEFAULT_DEPARTMENT)
        return ingest_observation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/recent-observations")
def recent(request: Request, limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    q = select(RawObservation)
    where_department = department_where(RawObservation, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    rows = list(
        db.scalars(
            q.order_by(
                func.coalesce(RawObservation.created_at, RawObservation.collected_at).desc(),
                RawObservation.id.desc(),
            ).limit(limit)
        ).all()
    )
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "platform": r.platform,
            "worker_id": r.worker_id,
            "account_id": r.account_id,
            "search_keyword": r.search_keyword,
            "content_hash": r.content_hash,
            "collected_at": _iso_or_text(r.collected_at),
            "created_at": _iso_or_text(r.created_at),
        })
    return {"ok": True, "items": out}
