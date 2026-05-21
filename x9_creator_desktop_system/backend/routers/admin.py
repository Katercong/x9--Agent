from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import os
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import DATA_DIR, settings
from ..database import get_db
from ..models.creator import Creator
from ..models.extension_session import ExtensionSession
from ..models.outreach_email import OutreachEmail
from ..models.raw_observation import RawObservation
from ..models.request_log import RequestLog
from ..models.review_task import ReviewTask
from ..models.system_log import SystemLog
from ..services import gmail_service, remote_creators
from ..services.departments import (
    DEPARTMENTS,
    current_user,
    current_department_code,
    department_where,
    effective_row_department,
    filter_rows_for_department,
    require_admin,
)


router = APIRouter(prefix="/api/local/admin", tags=["admin"])


RECOMMENDED_STATUSES = {"recommended", "recommended_after_review", "low_cost_test", "affiliate_test"}
BUSINESS_STATUS_ORDER = ("待建联", "已建联", "待回复", "已寄样", "视频已发布")


def require_super_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if user.get("role") != "super_admin" or user.get("entry_scope") != "admin":
        raise HTTPException(status_code=403, detail="super admin only")
    return user


def _creator_to_row(c: Creator) -> dict[str, Any]:
    return {
        "id": c.id,
        "department_code": c.department_code,
        "handle": c.handle,
        "display_name": c.display_name,
        "followers_count": c.followers_count,
        "email": c.email,
        "has_email": c.has_email,
        "collected_at": c.collected_at.isoformat() if c.collected_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "recommendation_status": c.recommendation_status,
        "current_status": c.current_status,
        "store_assigned": c.store_assigned,
        "owner_bd": c.owner_bd,
        "recommended_product_type": c.recommended_product_type,
        "recommended_collab_type": c.recommended_collab_type,
        "outreach_priority": c.outreach_priority,
        "queue_type": c.queue_type,
        "recommendation_score": c.recommendation_score,
        "primary_product_fit_score": c.primary_product_fit_score,
    }


def _local_rows(db: Session, department_code: str | None = None) -> list[dict[str, Any]]:
    q = select(Creator)
    where_department = department_where(Creator, department_code)
    if where_department is not None:
        q = q.where(where_department)
    return [_creator_to_row(row) for row in db.scalars(q).all()]


def _rows(db: Session, department_code: str | None = None) -> list[dict[str, Any]]:
    if settings.db_url.startswith("sqlite"):
        return _local_rows(db, department_code)
    try:
        return filter_rows_for_department(remote_creators.list_all(), department_code)
    except Exception:
        return _local_rows(db, department_code)


def _dashboard_summary(department_code: str | None) -> dict[str, Any]:
    try:
        from .dashboard import _build_summary  # noqa: WPS433

        return (_build_summary(department_code).get("summary") or {})
    except Exception:
        return {}


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _clean_group_key(value: Any, fallback: str = "未填写") -> str:
    text = str(value or "").strip()
    return text or fallback


def _count_by(rows: list[dict[str, Any]], key: str, *, fallback: str = "未填写") -> list[dict[str, Any]]:
    counts = Counter(_clean_group_key(row.get(key), fallback) for row in rows)
    return [
        {"name": name, "count": count}
        for name, count in counts.most_common()
    ]


def _row_date(row: dict[str, Any]):
    raw = str(row.get("collected_at") or row.get("created_at") or "")[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _outreach_count(db: Session, department_code: str | None, status: str | None = None) -> int:
    q = select(func.count(OutreachEmail.id))
    if status:
        q = q.where(OutreachEmail.status == status)
    where_department = department_where(OutreachEmail, department_code)
    if where_department is not None:
        q = q.where(where_department)
    return db.scalar(q) or 0


def _scope_payload(department_code: str | None) -> dict[str, str | None]:
    if department_code is None:
        return {"type": "company", "department_code": None, "name": "公司全局"}
    return {"type": "department", "department_code": department_code, "name": DEPARTMENTS[department_code]["name"]}


def _top_owner_rows(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        owner = _clean_group_key(row.get("owner_bd"))
        grouped.setdefault(owner, []).append(row)
    items = []
    for owner, owner_rows in grouped.items():
        status_counts = Counter(_clean_group_key(row.get("current_status")) for row in owner_rows)
        recommended = sum(1 for row in owner_rows if row.get("recommendation_status") in RECOMMENDED_STATUSES)
        items.append({
            "owner": owner,
            "creator_count": len(owner_rows),
            "recommended": recommended,
            "pending_contact": status_counts.get("待建联", 0),
            "contacted": status_counts.get("已建联", 0),
            "pending_reply": status_counts.get("待回复", 0),
            "sample_sent": status_counts.get("已寄样", 0),
            "video_published": status_counts.get("视频已发布", 0),
        })
    items.sort(key=lambda item: (-item["recommended"], -item["creator_count"], item["owner"]))
    return items[:limit]


def _recent_outreach_rows(db: Session, department_code: str | None, limit: int = 12) -> list[dict[str, Any]]:
    q = select(OutreachEmail).order_by(desc(OutreachEmail.created_at)).limit(limit)
    where_department = department_where(OutreachEmail, department_code)
    if where_department is not None:
        q = q.where(where_department)
    rows = db.scalars(q).all()
    return [
        {
            "creator_id": row.creator_id,
            "to_email": row.to_email,
            "from_email": row.from_email,
            "subject": row.subject,
            "status": row.status,
            "created_at": _iso(row.created_at),
            "sent_at": _iso(row.sent_at),
        }
        for row in rows
    ]


@router.get("/overview")
def overview(request: Request, _admin: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    rows = _rows(db, department_code)
    dept_counts = Counter(effective_row_department(row) for row in rows)
    status_counts = Counter(row.get("recommendation_status") or "unknown" for row in rows)
    queue_counts = Counter(row.get("queue_type") or "unknown" for row in rows)
    visible_departments = {department_code: DEPARTMENTS[department_code]} if department_code else DEPARTMENTS
    today = datetime.now().date()
    today_creators = sum(1 for row in rows if str(row.get("collected_at") or row.get("created_at") or "").startswith(str(today)))
    unified = _dashboard_summary(department_code)
    review_q = select(func.count(ReviewTask.id)).where(ReviewTask.status == "pending")
    outreach_q = select(func.count(OutreachEmail.id)).where(OutreachEmail.status == "sent")
    review_department = department_where(ReviewTask, department_code)
    outreach_department = department_where(OutreachEmail, department_code)
    if review_department is not None:
        review_q = review_q.where(review_department)
    if outreach_department is not None:
        outreach_q = outreach_q.where(outreach_department)
    return {
        "ok": True,
        "department_code": department_code,
        "total_creators": int(unified.get("total_creators") or len(rows)),
        "today_creators": int(unified.get("today_new_creators") or today_creators),
        "recent_30d_creators": int(unified.get("recent_30d_creators") or today_creators),
        "unique_creators": int(unified.get("unique_creators") or len(rows)),
        "all_channel_rows_total": int(unified.get("all_channel_rows_total") or unified.get("total_creators") or len(rows)),
        "recommended": sum(status_counts[s] for s in RECOMMENDED_STATUSES),
        "pending_review": db.scalar(review_q) or 0,
        "outreach_sent": db.scalar(outreach_q) or 0,
        "departments": [
            {
                "code": code,
                "name": meta["name"],
                "count": dept_counts.get(code, 0),
            }
            for code, meta in visible_departments.items()
        ],
        "status_counts": dict(status_counts),
        "queue_counts": dict(queue_counts),
    }


@router.get("/departments")
def departments(request: Request, _admin: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    rows = _rows(db, department_code)
    grouped: dict[str, list[dict]] = {code: [] for code in DEPARTMENTS}
    for row in rows:
        grouped.setdefault(effective_row_department(row), []).append(row)
    items = []
    visible_departments = {department_code: DEPARTMENTS[department_code]} if department_code else DEPARTMENTS
    for code, meta in visible_departments.items():
        dept_rows = grouped.get(code, [])
        recommended = sum(
            1 for row in dept_rows
            if row.get("recommendation_status") in RECOMMENDED_STATUSES
        )
        review_q = select(func.count(ReviewTask.id)).where(ReviewTask.status == "pending")
        extension_q = select(func.count(ExtensionSession.id))
        review_department = department_where(ReviewTask, code)
        extension_department = department_where(ExtensionSession, code)
        if review_department is not None:
            review_q = review_q.where(review_department)
        if extension_department is not None:
            extension_q = extension_q.where(extension_department)
        pending_review = db.scalar(review_q) or 0
        extension_count = db.scalar(extension_q) or 0
        items.append({
            "code": code,
            "name": meta["name"],
            "creator_count": len(dept_rows),
            "recommended": recommended,
            "pending_review": pending_review,
            "extension_count": extension_count,
        })
    return {"ok": True, "items": items}


@router.get("/business-dashboard")
def business_dashboard(request: Request, _user: dict = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    department_code = current_department_code(request)
    rows = _rows(db, department_code)
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)
    recommended_rows = [row for row in rows if row.get("recommendation_status") in RECOMMENDED_STATUSES]
    current_status_counts = Counter(_clean_group_key(row.get("current_status")) for row in rows)
    priority_counts = Counter(_clean_group_key(row.get("outreach_priority")) for row in rows)
    contacted_count = sum(current_status_counts.get(status, 0) for status in ("已建联", "待回复", "已寄样", "视频已发布"))
    recent_collection_count = sum(1 for row in rows if (_row_date(row) or datetime.min.date()) >= seven_days_ago)
    visible_departments = {department_code: DEPARTMENTS[department_code]} if department_code else DEPARTMENTS
    department_rows: dict[str, list[dict[str, Any]]] = {code: [] for code in visible_departments}
    for row in rows:
        department_rows.setdefault(effective_row_department(row), []).append(row)
    department_items = []
    for code, meta in visible_departments.items():
        dept_rows = department_rows.get(code, [])
        dept_status_counts = Counter(_clean_group_key(row.get("current_status")) for row in dept_rows)
        dept_recommended = sum(1 for row in dept_rows if row.get("recommendation_status") in RECOMMENDED_STATUSES)
        dept_contacted = sum(dept_status_counts.get(status, 0) for status in ("已建联", "待回复", "已寄样", "视频已发布"))
        department_items.append({
            "code": code,
            "name": meta["name"],
            "creator_count": len(dept_rows),
            "recommended": dept_recommended,
            "contacted": dept_contacted,
            "pending_contact": dept_status_counts.get("待建联", 0),
            "pending_reply": dept_status_counts.get("待回复", 0),
            "sample_sent": dept_status_counts.get("已寄样", 0),
            "video_published": dept_status_counts.get("视频已发布", 0),
        })
    return {
        "ok": True,
        "scope": _scope_payload(department_code),
        "summary": {
            "creator_count": len(rows),
            "recommended": len(recommended_rows),
            "contactable": sum(1 for row in rows if row.get("email") or row.get("has_email")),
            "assigned": sum(1 for row in rows if str(row.get("owner_bd") or "").strip()),
            "unassigned_recommended": sum(1 for row in recommended_rows if not str(row.get("owner_bd") or "").strip()),
            "contacted": contacted_count,
            "pending_contact": current_status_counts.get("待建联", 0),
            "pending_reply": current_status_counts.get("待回复", 0),
            "sample_sent": current_status_counts.get("已寄样", 0),
            "video_published": current_status_counts.get("视频已发布", 0),
            "recent_collections_7d": recent_collection_count,
            "outreach_drafts": _outreach_count(db, department_code, "draft"),
            "outreach_sent": _outreach_count(db, department_code, "sent"),
            "outreach_failed": _outreach_count(db, department_code, "failed"),
        },
        "business_status": [
            {"name": status, "count": current_status_counts.get(status, 0)}
            for status in BUSINESS_STATUS_ORDER
        ] + [
            {"name": name, "count": count}
            for name, count in current_status_counts.most_common()
            if name not in BUSINESS_STATUS_ORDER
        ],
        "products": _count_by(rows, "recommended_product_type"),
        "collab_types": _count_by(rows, "recommended_collab_type"),
        "priorities": [
            {"name": name, "count": priority_counts.get(name, 0)}
            for name in ("P1", "P2", "P3", "P4")
            if priority_counts.get(name, 0)
        ] + [
            {"name": name, "count": count}
            for name, count in priority_counts.most_common()
            if name not in {"P1", "P2", "P3", "P4"}
        ],
        "queues": _count_by(rows, "queue_type"),
        "owners": _top_owner_rows(rows),
        "departments": department_items,
        "recent_outreach": _recent_outreach_rows(db, department_code),
    }


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if "://" not in value or "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" not in creds:
        return f"{scheme}://***@{host}"
    user, _password = creds.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


def _safe_count(db: Session, model: Any) -> int:
    try:
        return int(db.scalar(select(func.count(model.id))) or 0)
    except Exception:
        return 0


def _cpu_percent() -> int | None:
    try:
        if os.name == "nt":
            kwargs: dict[str, Any] = {}
            kwargs["creationflags"] = 0x08000000
            proc = subprocess.run(
                ["wmic", "cpu", "get", "loadpercentage", "/value"],
                capture_output=True,
                text=True,
                timeout=2,
                **kwargs,
            )
            for line in proc.stdout.splitlines():
                if line.strip().lower().startswith("loadpercentage="):
                    return max(0, min(100, int(line.split("=", 1)[1].strip())))
        load = os.getloadavg()[0]
        cpu_count = os.cpu_count() or 1
        return max(0, min(100, round((load / cpu_count) * 100)))
    except Exception:
        return None


def _request_buckets(db: Session) -> tuple[list[dict[str, Any]], int, int, int]:
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    first_hour = now - timedelta(hours=23)
    buckets: dict[datetime, int] = {
        first_hour + timedelta(hours=i): 0
        for i in range(24)
    }
    rows = db.execute(
        select(RequestLog.ts, RequestLog.status_code, RequestLog.duration_ms)
        .where(RequestLog.ts >= first_hour)
    ).all()
    total_duration = 0
    duration_count = 0
    error_count = 0
    for ts, status_code, duration_ms in rows:
        if not ts:
            continue
        hour = ts.replace(minute=0, second=0, microsecond=0)
        if hour in buckets:
            buckets[hour] += 1
        if duration_ms is not None:
            total_duration += int(duration_ms)
            duration_count += 1
        if int(status_code or 0) >= 500:
            error_count += 1
    items = [
        {"hour": key.strftime("%H:00"), "count": count}
        for key, count in sorted(buckets.items())
    ]
    avg_duration = round(total_duration / duration_count) if duration_count else 0
    return items, len(rows), avg_duration, error_count


@router.get("/system-metrics")
def system_metrics(_admin: dict = Depends(require_super_admin), db: Session = Depends(get_db)) -> dict:
    disk = shutil.disk_usage(DATA_DIR)
    disk_percent = round((disk.used / disk.total) * 100) if disk.total else 0
    table_counts = [
        {"name": "creators", "count": _safe_count(db, Creator)},
        {"name": "raw_observations", "count": _safe_count(db, RawObservation)},
        {"name": "outreach_emails", "count": _safe_count(db, OutreachEmail)},
        {"name": "review_tasks", "count": _safe_count(db, ReviewTask)},
        {"name": "extension_sessions", "count": _safe_count(db, ExtensionSession)},
        {"name": "system_logs", "count": _safe_count(db, SystemLog)},
        {"name": "request_logs", "count": _safe_count(db, RequestLog)},
    ]
    requests_24h, request_total, avg_duration, error_count = _request_buckets(db)
    return {
        "ok": True,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cpu_percent": _cpu_percent(),
        "disk": {
            "path": str(DATA_DIR),
            "percent": disk_percent,
            "used": disk.used,
            "free": disk.free,
            "total": disk.total,
        },
        "database": {
            "row_count": sum(item["count"] for item in table_counts),
            "tables": table_counts,
        },
        "requests_24h": requests_24h,
        "request_total_24h": request_total,
        "avg_duration_ms_24h": avg_duration,
        "error_count_24h": error_count,
    }


@router.get("/system-settings")
def system_settings(_admin: dict = Depends(require_super_admin)) -> dict:
    gmail_status = gmail_service.status()
    return {
        "ok": True,
        "app": {
            "service": settings.app_name,
            "env": settings.app_env,
            "system_version": settings.system_version,
            "backend_port": settings.backend_port,
            "score_version": settings.score_version,
            "tag_version": settings.tag_version,
            "rec_version": settings.rec_version,
        },
        "database": {
            "url": _mask_secret(settings.db_url),
            "remote_api_url": settings.remote_api_url,
            "remote_table": settings.remote_table,
            "remote_timeout": settings.remote_timeout,
        },
        "ai": {
            "openai_configured": bool(settings.openai_api_key),
            "openai_model": settings.openai_model,
            "openai_base_url": settings.openai_base_url,
            "openai_timeout": settings.openai_timeout,
        },
        "gmail": {
            "configured": bool(gmail_status.get("configured")),
            "configured_source": gmail_status.get("configured_source"),
            "authorized": bool(gmail_status.get("authorized")),
            "account_count": len(gmail_status.get("accounts") or []),
            "client_id": gmail_service.public_client_id() or "",
            "client_secret_path": gmail_status.get("client_secret_path"),
            "javascript_origins": gmail_service.public_javascript_origins(),
            "redirect_uri": gmail_status.get("redirect_uri"),
            "public_base_url": gmail_status.get("public_base_url"),
            "scopes": gmail_status.get("scopes") or [],
        },
        "departments": [
            {"code": code, "slug": meta["slug"], "name": meta["name"]}
            for code, meta in DEPARTMENTS.items()
        ],
    }


@router.get("/trends")
def trends(request: Request, days: int = 14, _admin: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    days = max(1, min(days, 90))
    department_code = current_department_code(request)
    visible_departments = {department_code: DEPARTMENTS[department_code]} if department_code else DEPARTMENTS
    start = datetime.now().date() - timedelta(days=days - 1)
    buckets = {
        (start + timedelta(days=i)).isoformat(): {code: 0 for code in visible_departments}
        for i in range(days)
    }
    for row in _rows(db, department_code):
        raw = str(row.get("collected_at") or row.get("created_at") or "")[:10]
        if raw in buckets:
            buckets[raw][effective_row_department(row)] = buckets[raw].get(effective_row_department(row), 0) + 1
    obs_q = select(RawObservation.department_code, RawObservation.created_at)
    obs_department = department_where(RawObservation, department_code)
    if obs_department is not None:
        obs_q = obs_q.where(obs_department)
    observations = {day: {code: 0 for code in visible_departments} for day in buckets}
    for dept, created_at in db.execute(obs_q).all():
        day_key = str(created_at or "")[:10]
        if day_key in observations:
            dept_key = dept or "cross_border"
            observations[day_key][dept_key] = observations[day_key].get(dept_key, 0) + 1
    return {"ok": True, "creator_collections": buckets, "raw_observations": observations}


@router.get("/extensions")
def extensions(request: Request, _admin: dict = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    q = select(ExtensionSession).order_by(ExtensionSession.last_heartbeat_at.desc())
    where_department = department_where(ExtensionSession, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    rows = list(db.scalars(q).all())
    return {
        "ok": True,
        "items": [
            {
                "department_code": row.department_code,
                "worker_id": row.worker_id,
                "extension_version": row.extension_version,
                "status": row.status,
                "current_url": row.current_url,
                "tiktok_login_status": row.tiktok_login_status,
                "last_heartbeat_at": _iso(row.last_heartbeat_at),
            }
            for row in rows
        ],
    }
