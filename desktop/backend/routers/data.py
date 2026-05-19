"""Generic read API over the desktop x9db, shape-compatible with the legacy
core `GET /api/v1/data/{resource}` contract so the admin SPA can read its
real data from THIS database instead of the core proxy.

Only resources that actually exist in x9db are mapped. Core-only resources
(products, categories, webhooks, llm_*, keyword_snapshots, api_metrics,
business_metrics_daily, named_queries, notifications) are intentionally NOT
here — that data does not live in x9db.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.app_user import AppUser
from ..models.creator import Creator
from ..models.creator_recommendation import CreatorRecommendation
from ..models.creator_tag import CreatorTag
from ..models.extension_command import ExtensionCommand
from ..models.extension_run_progress import ExtensionRunProgress
from ..models.extension_session import ExtensionSession
from ..models.outreach_email import OutreachEmail
from ..models.outreach_template import OutreachTemplate
from ..models.raw_observation import RawObservation
from ..models.review_task import ReviewTask
from ..models.system_log import SystemLog
from ..models.tag_definition import TagDefinition
from ..services.departments import current_department_code, department_where

router = APIRouter(prefix="/api/local/data", tags=["data"])

# Admin-SPA resource name -> x9db model. audit_log maps to system_logs so the
# /a/audit page reads the desktop log table.
RESOURCE_MODELS: dict[str, Any] = {
    "creators": Creator,
    "outreach": OutreachEmail,
    "outreach_emails": OutreachEmail,
    "outreach_templates": OutreachTemplate,
    "review_tasks": ReviewTask,
    "raw_observations": RawObservation,
    "extension_sessions": ExtensionSession,
    "extension_commands": ExtensionCommand,
    "extension_run_progress": ExtensionRunProgress,
    "creator_recommendations": CreatorRecommendation,
    "creator_tags": CreatorTag,
    "tag_definitions": TagDefinition,
    "system_logs": SystemLog,
    "audit_log": SystemLog,
    "app_users": AppUser,
    "users": AppUser,
}

# Never serialize these out, regardless of model.
_SENSITIVE = {"password_hash", "token_json", "password", "secret", "refresh_token", "access_token"}


def _columns(model: Any) -> list[str]:
    return [c.key for c in inspect(model).mapper.column_attrs]


def _serialize(row: Any, cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in cols:
        if k in _SENSITIVE:
            continue
        v = getattr(row, k, None)
        if isinstance(v, (datetime, date)):
            v = v.isoformat()
        out[k] = v
    return out


def _model_or_404(resource: str):
    model = RESOURCE_MODELS.get(resource)
    if model is None:
        raise HTTPException(status_code=404, detail=f"resource '{resource}' is not backed by x9db")
    return model


@router.get("/{resource}")
def list_resource(
    resource: str,
    request: Request,
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
    order_by: str | None = Query(default=None),
    desc: bool = Query(default=True),
) -> dict:
    model = _model_or_404(resource)
    cols = _columns(model)
    colset = set(cols)

    stmt = select(model)

    # Department scoping (same pattern as collector.py) when the model carries it.
    if "department_code" in colset:
        where_dep = department_where(model, current_department_code(request))
        if where_dep is not None:
            stmt = stmt.where(where_dep)

    # Free-text search across string-ish columns.
    if q:
        like = f"%{q.strip()}%"
        text_cols = [
            getattr(model, c.key)
            for c in inspect(model).mapper.column_attrs
            if c.key not in _SENSITIVE and str(c.expression.type).upper().split("(")[0]
            in {"VARCHAR", "TEXT", "STRING", "CHAR"}
        ]
        if text_cols:
            stmt = stmt.where(or_(*[col.ilike(like) for col in text_cols]))

    # Simple equality / __icontains filters from remaining query params.
    reserved = {"limit", "offset", "q", "order_by", "desc"}
    for key, value in request.query_params.items():
        if key in reserved:
            continue
        if key.endswith("__icontains"):
            base = key[: -len("__icontains")]
            if base in colset:
                stmt = stmt.where(getattr(model, base).ilike(f"%{value}%"))
        elif key in colset:
            stmt = stmt.where(getattr(model, key) == value)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_col = order_by if (order_by and order_by in colset) else ("created_at" if "created_at" in colset else cols[0])
    order_expr = getattr(model, sort_col)
    stmt = stmt.order_by(order_expr.desc() if desc else order_expr.asc())
    stmt = stmt.limit(limit).offset(offset)

    rows = list(db.scalars(stmt).all())
    items = [_serialize(r, cols) for r in rows]
    return {"resource": resource, "total": int(total), "limit": limit, "offset": offset, "items": items}


@router.get("/{resource}/{row_id}")
def get_row(resource: str, row_id: str, db: Session = Depends(get_db)) -> dict:
    model = _model_or_404(resource)
    cols = _columns(model)
    pk = inspect(model).primary_key[0]
    row = db.scalar(select(model).where(pk == row_id))
    if row is None:
        raise HTTPException(status_code=404, detail="row not found")
    return _serialize(row, cols)
