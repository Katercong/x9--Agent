from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.departments import current_department_code
from ..services.review_task_service import list_tasks, update_task
from ..utils.json_utils import loads_json_list


router = APIRouter(prefix="/api/local/review-tasks", tags=["review-tasks"])


class ReviewTaskUpdateIn(BaseModel):
    status: str | None = None
    reviewer_notes: str | None = None
    review_result: str | None = None
    assigned_staff_id: str | None = None
    change_product_type: str | None = None
    change_collab_type: str | None = None
    upgrade_priority: str | None = None


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _serialize(t) -> dict:
    return {
        "id": t.id,
        "creator_id": t.creator_id,
        "task_type": t.task_type,
        "status": t.status,
        "risk_tags": loads_json_list(t.risk_tags_json),
        "reason": t.reason,
        "reviewer_notes": t.reviewer_notes,
        "review_result": t.review_result,
        "assigned_staff_id": t.assigned_staff_id,
        "created_at": _iso(t.created_at),
        "reviewed_at": _iso(t.reviewed_at),
    }


@router.get("")
def list_endpoint(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    rows = list_tasks(db, status=status, limit=limit, offset=offset, department_code=current_department_code(request))
    return {"ok": True, "total": len(rows), "items": [_serialize(t) for t in rows]}


@router.patch("/{task_id}")
def patch_endpoint(task_id: str, body: ReviewTaskUpdateIn, request: Request, db: Session = Depends(get_db)) -> dict:
    t = update_task(
        db,
        task_id,
        status=body.status,
        reviewer_notes=body.reviewer_notes,
        review_result=body.review_result,
        assigned_staff_id=body.assigned_staff_id,
        change_product_type=body.change_product_type,
        change_collab_type=body.change_collab_type,
        upgrade_priority=body.upgrade_priority,
        department_code=current_department_code(request),
    )
    if t is None:
        raise HTTPException(status_code=404, detail="review task not found")
    return _serialize(t)
