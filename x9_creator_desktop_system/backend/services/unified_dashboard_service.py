from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.creator_outreach_event import CreatorOutreachEvent
from ..models.followup_task import FollowupTask
from ..models.gmail_account import GmailAccount
from ..models.gmail_sync_state import GmailSyncState
from ..models.outreach_email import OutreachEmail
from ..models.raw_observation import RawObservation
from .departments import DEFAULT_DEPARTMENT, department_where, normalize_department_code


RECOMMENDED_STATUSES = {
    "recommended",
    "recommended_after_review",
    "low_cost_test",
    "affiliate_test",
    "brand_awareness_only",
    "manual_review_before_outreach",
}
RAW_QUEUE_LEAD_STATUSES = ("shop_list_seen", "shop_queue_cleared")

SUMMARY_KEYS = (
    "total_discovered",
    "total_collected",
    "today_discovered",
    "today_collected",
    "today_duplicate_creators",
    "total_recommended",
    "pending_contact",
    "pending_reply",
    "communicating",
    "sample_shipped",
    "sample_delivered",
    "video_published",
    "ad_authorized",
    "ad_running",
)

STAGE_ORDER = (
    "discovered",
    "recommended",
    "pending_contact",
    "pending_reply",
    "communicating",
    "sample_shipped",
    "sample_delivered",
    "video_published",
    "ad_authorized",
    "ad_running",
)
STAGE_RANK = {stage: index for index, stage in enumerate(STAGE_ORDER)}
STAGE_LABELS = {
    "discovered": "\u53d1\u73b0",
    "recommended": "\u63a8\u8350",
    "pending_contact": "\u5f85\u5efa\u8054",
    "pending_reply": "\u5f85\u56de\u590d",
    "communicating": "\u6c9f\u901a\u4e2d",
    "sample_shipped": "\u5df2\u5bc4\u6837",
    "sample_delivered": "\u6837\u54c1\u7b7e\u6536",
    "video_published": "\u89c6\u9891\u5df2\u53d1",
    "ad_authorized": "\u5df2\u6388\u6743",
    "ad_running": "\u5e7f\u544a\u6295\u653e\u4e2d",
}

EVENT_STAGE_ALIASES = {
    "recommended": "recommended",
    "assigned": "pending_contact",
    "sent": "pending_reply",
    "email_sent": "pending_reply",
    "pending_reply": "pending_reply",
    "awaiting_reply": "pending_reply",
    "waiting_reply": "pending_reply",
    "contacted": "communicating",
    "replied": "communicating",
    "reply_received": "communicating",
    "communicating": "communicating",
    "confirmed": "communicating",
    "address_confirmed": "communicating",
    "cooperation_confirmed": "communicating",
    "content_plan": "communicating",
    "content_planning": "communicating",
    "sample_shipped": "sample_shipped",
    "sample_sent": "sample_shipped",
    "sent_sample": "sample_shipped",
    "sample_delivered": "sample_delivered",
    "delivered": "sample_delivered",
    "video_published": "video_published",
    "published": "video_published",
    "partnered": "ad_authorized",
    "ad_authorized": "ad_authorized",
    "authorized": "ad_authorized",
    "ad_running": "ad_running",
    "ad_started": "ad_running",
    "running": "ad_running",
}

STATUS_STAGE_ALIASES = {
    "prospect": "discovered",
    "lead": "discovered",
    "recommended": "recommended",
    "pending_contact": "pending_contact",
    "\u5f85\u5efa\u8054": "pending_contact",
    "\u5f85\u8054\u7cfb": "pending_contact",
    "contacted": "communicating",
    "\u5df2\u5efa\u8054": "pending_reply",
    "\u5df2\u8054\u7cfb": "pending_reply",
    "pending_reply": "pending_reply",
    "awaiting_reply": "pending_reply",
    "\u5f85\u56de\u590d": "pending_reply",
    "communicating": "communicating",
    "confirmed": "communicating",
    "replied": "communicating",
    "\u6c9f\u901a\u4e2d": "communicating",
    "\u5df2\u56de\u590d": "communicating",
    "\u5df2\u786e\u8ba4": "communicating",
    "\u786e\u8ba4\u5408\u4f5c": "communicating",
    "sample_shipped": "sample_shipped",
    "sample_sent": "sample_shipped",
    "\u5df2\u5bc4\u6837": "sample_shipped",
    "sample_delivered": "sample_delivered",
    "delivered": "sample_delivered",
    "\u6837\u54c1\u7b7e\u6536": "sample_delivered",
    "video_published": "video_published",
    "published": "video_published",
    "\u89c6\u9891\u5df2\u53d1": "video_published",
    "\u89c6\u9891\u5df2\u53d1\u5e03": "video_published",
    "ad_authorized": "ad_authorized",
    "authorized": "ad_authorized",
    "\u5df2\u6388\u6743": "ad_authorized",
    "ad_running": "ad_running",
    "running": "ad_running",
    "\u5e7f\u544a\u6295\u653e\u4e2d": "ad_running",
}


def build_unified_dashboard(
    db: Session,
    *,
    scope_type: str,
    department_code: str | None = None,
) -> dict[str, Any]:
    dept = normalize_department_code(department_code, default=None) if department_code else None
    now = datetime.utcnow()
    local_today = datetime.now().date()
    today_start = datetime.combine(local_today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    creators = _creator_rows(db, dept)
    creator_ids = {str(row["id"]) for row in creators}
    events_by_creator = _events_by_creator(db, dept, creator_ids)
    sent_email_creators = _sent_email_creator_ids(db, dept, creator_ids)

    stage_counts: Counter[str] = Counter()
    total_recommended = 0
    for creator in creators:
        if _is_recommended(creator.get("recommendation_status")):
            total_recommended += 1
        stage = project_creator_stage(
            current_status=creator.get("current_status"),
            recommendation_status=creator.get("recommendation_status"),
            owner_bd=creator.get("owner_bd"),
            events=events_by_creator.get(str(creator["id"]), ()),
            has_sent_email=str(creator["id"]) in sent_email_creators,
        )
        stage_counts[stage] += 1

    total_collected = _raw_observation_count(db, dept, exclude_queue=True)
    total_discovered = _total_discovered_count(db, dept)
    today_discovered = _raw_observation_count(db, dept, start=today_start, end=tomorrow_start)
    today_collected = _raw_observation_count(db, dept, start=today_start, end=tomorrow_start, exclude_queue=True)
    today_duplicate_creators = _today_duplicate_creator_count(db, dept, local_today)
    summary = {
        "total_discovered": total_discovered,
        "total_collected": total_collected,
        "today_discovered": today_discovered,
        "today_collected": today_collected,
        "today_duplicate_creators": today_duplicate_creators,
        "total_recommended": total_recommended,
        "pending_contact": stage_counts.get("pending_contact", 0),
        "pending_reply": stage_counts.get("pending_reply", 0),
        "communicating": stage_counts.get("communicating", 0),
        "sample_shipped": stage_counts.get("sample_shipped", 0),
        "sample_delivered": stage_counts.get("sample_delivered", 0),
        "video_published": stage_counts.get("video_published", 0),
        "ad_authorized": stage_counts.get("ad_authorized", 0),
        "ad_running": stage_counts.get("ad_running", 0),
    }
    summary = {key: int(summary.get(key, 0) or 0) for key in SUMMARY_KEYS}

    return {
        "ok": True,
        "generated_at": f"{now.isoformat()}Z",
        "scope": {"type": scope_type, "department_code": dept},
        "summary": summary,
        "stage_rows": [
            {"key": stage, "name": STAGE_LABELS[stage], "count": int(stage_counts.get(stage, 0))}
            for stage in STAGE_ORDER
        ],
        "followups": _followup_payload(db, dept, now),
        "gmail_sync": _gmail_sync_payload(db, dept, now),
    }


def project_creator_stage(
    *,
    current_status: Any = None,
    recommendation_status: Any = None,
    owner_bd: Any = None,
    events: list[str] | tuple[str, ...] = (),
    has_sent_email: bool = False,
) -> str:
    candidates = ["discovered"]
    if _is_recommended(recommendation_status):
        candidates.extend(["recommended", "pending_contact"])
    if str(owner_bd or "").strip() and _is_recommended(recommendation_status):
        candidates.append("pending_contact")
    if has_sent_email:
        candidates.append("pending_reply")
    status_stage = _status_to_stage(current_status)
    if status_stage:
        candidates.append(status_stage)
    for event_type in events:
        stage = EVENT_STAGE_ALIASES.get(_normalize_key(event_type))
        if stage:
            candidates.append(stage)
    return max(candidates, key=lambda stage: STAGE_RANK.get(stage, 0))


def _creator_rows(db: Session, department_code: str | None) -> list[dict[str, Any]]:
    stmt = select(
        Creator.id,
        Creator.department_code,
        Creator.current_status,
        Creator.recommendation_status,
        Creator.owner_bd,
        Creator.collected_at,
    )
    where_department = department_where(Creator, department_code)
    if where_department is not None:
        stmt = stmt.where(where_department)
    return [dict(row) for row in db.execute(stmt).mappings().all()]


def _events_by_creator(
    db: Session,
    department_code: str | None,
    creator_ids: set[str],
) -> dict[str, list[str]]:
    if not creator_ids:
        return {}
    stmt = select(CreatorOutreachEvent.creator_id, CreatorOutreachEvent.event_type)
    where_department = department_where(CreatorOutreachEvent, department_code)
    if where_department is not None:
        stmt = stmt.where(where_department)
    rows = db.execute(stmt).mappings().all()
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        creator_id = str(row["creator_id"])
        if creator_id in creator_ids:
            grouped[creator_id].append(str(row["event_type"] or ""))
    return grouped


def _sent_email_creator_ids(db: Session, department_code: str | None, creator_ids: set[str]) -> set[str]:
    if not creator_ids:
        return set()
    stmt = select(OutreachEmail.creator_id).where(OutreachEmail.status == "sent")
    where_department = department_where(OutreachEmail, department_code)
    if where_department is not None:
        stmt = stmt.where(where_department)
    return {str(row[0]) for row in db.execute(stmt).all() if str(row[0]) in creator_ids}


def _raw_observation_count(
    db: Session,
    department_code: str | None,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    exclude_queue: bool = False,
) -> int:
    if start is not None or end is not None:
        clauses = []
        params: dict[str, Any] = {}
        if department_code:
            params["department_code"] = department_code
            if department_code == DEFAULT_DEPARTMENT:
                clauses.append("(department_code = :department_code OR department_code IS NULL OR department_code = '')")
            else:
                clauses.append("department_code = :department_code")
        if start is not None:
            clauses.append("DATE(collected_at) >= :start_date")
            params["start_date"] = start.date().isoformat()
        if end is not None:
            clauses.append("DATE(collected_at) < :end_date")
            params["end_date"] = end.date().isoformat()
        if exclude_queue:
            queue_placeholders = []
            for index, status in enumerate(RAW_QUEUE_LEAD_STATUSES):
                key = f"queue_status_{index}"
                queue_placeholders.append(f":{key}")
                params[key] = status
            clauses.append(f"COALESCE(lead_status, '') NOT IN ({', '.join(queue_placeholders)})")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return int(db.execute(text(f"SELECT COUNT(*) FROM raw_observations{where}"), params).scalar() or 0)

    stmt = select(func.count()).select_from(RawObservation)
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        stmt = stmt.where(where_department)
    if exclude_queue:
        stmt = stmt.where(func.coalesce(RawObservation.lead_status, "").notin_(RAW_QUEUE_LEAD_STATUSES))
    if start is not None:
        stmt = stmt.where(RawObservation.collected_at >= start)
    if end is not None:
        stmt = stmt.where(RawObservation.collected_at < end)
    return int(db.scalar(stmt) or 0)


def _total_discovered_count(db: Session, department_code: str | None) -> int:
    total = 0
    for table in ("creators", "creator", "tk_creators", "raw_observations"):
        total += _table_row_count(db, table, department_code)
    return total


def _today_duplicate_creator_count(db: Session, department_code: str | None, today: date) -> int:
    inspector = inspect(db.bind)
    table_names = set(inspector.get_table_names())
    if "creator_sources" not in table_names or "raw_observations" not in table_names:
        return 0

    clauses = ["DATE(r.collected_at) = :today"]
    params: dict[str, Any] = {"today": today.isoformat()}
    if department_code:
        params["department_code"] = department_code
        if department_code == DEFAULT_DEPARTMENT:
            clauses.append("(cs.department_code = :department_code OR cs.department_code IS NULL OR cs.department_code = '')")
        else:
            clauses.append("cs.department_code = :department_code")
    clauses.append(
        """(
            (cs.first_seen_at IS NOT NULL AND DATE(cs.first_seen_at) < :today)
            OR (c.created_at IS NOT NULL AND DATE(c.created_at) < :today)
        )"""
    )
    where = " AND ".join(clauses)
    sql = f"""
        SELECT COUNT(DISTINCT cs.creator_id)
        FROM creator_sources cs
        JOIN raw_observations r ON r.id = cs.raw_observation_id
        LEFT JOIN creators c ON c.id = cs.creator_id
        WHERE {where}
    """
    return int(db.execute(text(sql), params).scalar() or 0)


def _table_row_count(db: Session, table: str, department_code: str | None) -> int:
    inspector = inspect(db.bind)
    if table not in inspector.get_table_names():
        return 0
    columns = {column["name"] for column in inspector.get_columns(table)}
    clauses = []
    params: dict[str, Any] = {}
    if department_code and "department_code" in columns:
        params["department_code"] = department_code
        if department_code == DEFAULT_DEPARTMENT:
            clauses.append("(department_code = :department_code OR department_code IS NULL OR department_code = '')")
        else:
            clauses.append("department_code = :department_code")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return int(db.execute(text(f"SELECT COUNT(*) FROM {table}{where}"), params).scalar() or 0)


def _followup_payload(db: Session, department_code: str | None, now: datetime) -> dict[str, Any]:
    open_statuses = ("open", "pending")
    today_start = datetime.combine(now.date(), datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    base = select(FollowupTask).where(FollowupTask.status.in_(open_statuses))
    where_department = department_where(FollowupTask, department_code)
    if where_department is not None:
        base = base.where(where_department)
    overdue = int(db.scalar(select(func.count()).select_from(base.where(FollowupTask.due_at < today_start).subquery())) or 0)
    due_today = int(db.scalar(select(func.count()).select_from(base.where(FollowupTask.due_at >= today_start, FollowupTask.due_at < tomorrow_start).subquery())) or 0)
    rows = db.scalars(base.order_by(FollowupTask.due_at.asc(), FollowupTask.priority.desc()).limit(10)).all()
    return {
        "overdue": overdue,
        "due_today": due_today,
        "items": [_followup_item(row) for row in rows],
    }


def _gmail_sync_payload(db: Session, department_code: str | None, now: datetime) -> dict[str, Any]:
    stmt = select(GmailAccount)
    where_department = department_where(GmailAccount, department_code)
    if where_department is not None:
        stmt = stmt.where(where_department)
    accounts = db.scalars(stmt.order_by(GmailAccount.is_default.desc(), GmailAccount.email.asc())).all()
    state_by_account = {
        state.account_id: state
        for state in db.scalars(select(GmailSyncState)).all()
    }
    return {
        "accounts": [
            _gmail_account_item(account, state_by_account.get(account.id), now)
            for account in accounts
        ]
    }


def _followup_item(row: FollowupTask) -> dict[str, Any]:
    return {
        "id": row.id,
        "creator_id": row.creator_id,
        "department_code": row.department_code,
        "owner_user_id": row.owner_user_id,
        "task_type": row.task_type,
        "status": row.status,
        "due_at": _iso(row.due_at),
        "completed_at": _iso(row.completed_at),
        "priority": row.priority,
        "reason": row.reason,
        "metadata": _json(row.metadata_json),
    }


def _gmail_account_item(account: GmailAccount, state: GmailSyncState | None, now: datetime) -> dict[str, Any]:
    readonly_ok = _token_has_readonly_scope(account.token_json)
    active_interval = 10 if _recent(account.last_used_at, now, days=7) else 30
    interval = int(getattr(state, "interval_minutes", None) or active_interval)
    return {
        "account_id": account.id,
        "email": account.email,
        "department_code": account.department_code,
        "is_active": int(account.is_active or 0),
        "is_default": int(account.is_default or 0),
        "last_history_id": getattr(state, "last_history_id", None),
        "last_sync_at": _iso(getattr(state, "last_sync_at", None)),
        "next_sync_at": _iso(getattr(state, "next_sync_at", None)),
        "interval_minutes": interval,
        "status": getattr(state, "status", None) or ("idle" if readonly_ok else "reauth_required"),
        "error_message": getattr(state, "error_message", None),
        "readonly_scope": readonly_ok,
        "reauthorization_required": not readonly_ok,
    }


def _status_to_stage(value: Any) -> str | None:
    return STATUS_STAGE_ALIASES.get(_normalize_key(value))


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _is_recommended(value: Any) -> bool:
    return _normalize_key(value) in RECOMMENDED_STATUSES


def _same_day(value: Any, day: date) -> bool:
    dt = _as_datetime(value)
    return bool(dt and dt.date() == day)


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    dt = _as_datetime(value)
    if dt is None:
        return None
    return dt.isoformat()


def _json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _token_has_readonly_scope(token_json: str | None) -> bool:
    scopes: Any
    try:
        token = json.loads(token_json or "{}")
    except (TypeError, ValueError):
        token = {}
    scopes = token.get("scopes") or token.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return "https://www.googleapis.com/auth/gmail.readonly" in set(scopes or [])


def _recent(value: Any, now: datetime, *, days: int) -> bool:
    dt = _as_datetime(value)
    return bool(dt and dt >= now - timedelta(days=days))
