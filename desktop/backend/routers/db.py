from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db, init_db
from ..models import (
    Creator,
    CreatorTag,
    CreatorRecommendation,
    ExtensionSession,
    RawObservation,
    ReviewTask,
    SystemLog,
    TagDefinition,
)
from ..services import remote_creators
from ..services.departments import current_department_code, department_where, filter_rows_for_department


router = APIRouter(prefix="/api/local/db", tags=["db"])


@router.get("/status")
def db_status(db: Session = Depends(get_db)) -> dict:
    return {"ok": True, "url": settings.db_url}


@router.post("/migrate")
def migrate() -> dict:
    init_db()
    return {"ok": True, "action": "migrate", "url": settings.db_url}


def _count(db: Session, model, department_code: str | None) -> int:
    q = select(func.count(model.id))
    where_department = department_where(model, department_code)
    if where_department is not None:
        q = q.where(where_department)
    return db.scalar(q) or 0


def _today_prefix() -> str:
    return datetime.now().date().isoformat()


def _count_today(db: Session, model, department_code: str | None, *date_columns) -> int:
    date_expr = date_columns[0] if len(date_columns) == 1 else func.coalesce(*date_columns)
    q = select(func.count(model.id)).where(cast(date_expr, String).like(f"{_today_prefix()}%"))
    where_department = department_where(model, department_code)
    if where_department is not None:
        q = q.where(where_department)
    return db.scalar(q) or 0


@router.get("/stats")
def stats(request: Request, db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    try:
        creator_total = len(filter_rows_for_department(remote_creators.list_all(), department_code))
    except Exception:
        creator_total = _count(db, Creator, department_code)
    creator_today = _count_today(db, Creator, department_code, Creator.collected_at, Creator.created_at)
    raw_observations_today = _count_today(
        db,
        RawObservation,
        department_code,
        RawObservation.collected_at,
        RawObservation.created_at,
    )
    return {
        "creators": creator_total,
        "today_creators": creator_today,
        "creators_today": creator_today,
        "raw_observations": _count(db, RawObservation, department_code),
        "today_raw_observations": raw_observations_today,
        "raw_observations_today": raw_observations_today,
        "creator_tags": _count(db, CreatorTag, department_code),
        "tag_definitions": db.scalar(select(func.count(TagDefinition.tag_code))) or 0,
        "review_tasks": _count(db, ReviewTask, department_code),
        "creator_recommendations": _count(db, CreatorRecommendation, department_code),
        "extension_sessions": _count(db, ExtensionSession, department_code),
        "system_logs": db.scalar(select(func.count(SystemLog.id))) or 0,
    }
