from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from ..database.connection import engine
from ..services.departments import (
    DEFAULT_DEPARTMENT,
    DEPARTMENTS,
    current_department_code,
    current_user,
)


router = APIRouter(prefix="/api/local/dashboard", tags=["dashboard"])


_HANDLE_RE = re.compile(r"^@+")
_SIMPLE_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

STAGE_META: dict[str, dict[str, Any]] = {
    "prospect": {"label": "潜在线索", "rank": 10},
    "contacted": {"label": "已联系", "rank": 20},
    "pending_reply": {"label": "待回复", "rank": 25},
    "confirmed": {"label": "已确认", "rank": 30},
    "sample_shipped": {"label": "已寄样", "rank": 40},
    "sample_delivered": {"label": "样品签收", "rank": 50},
    "video_published": {"label": "视频已发", "rank": 60},
    "ad_authorized": {"label": "已授权", "rank": 70},
    "ad_running": {"label": "广告投放中", "rank": 80},
    "dropped": {"label": "已放弃", "rank": 90},
}
STAGE_ORDER = list(STAGE_META)

_STAGE_ALIASES = {
    "prospect": "prospect",
    "lead": "prospect",
    "pending": "prospect",
    "待建联": "prospect",
    "未建联": "prospect",
    "待联系": "prospect",
    "潜在": "prospect",
    "潜在线索": "prospect",
    "contacted": "contacted",
    "sent": "contacted",
    "queued": "contacted",
    "outreached": "contacted",
    "已建联": "contacted",
    "建联": "contacted",
    "已联系": "contacted",
    "已触达": "contacted",
    "pending_reply": "pending_reply",
    "awaiting_reply": "pending_reply",
    "waiting_reply": "pending_reply",
    "待回复": "pending_reply",
    "等待回复": "pending_reply",
    "未回复": "pending_reply",
    "confirmed": "confirmed",
    "已确认": "confirmed",
    "确认合作": "confirmed",
    "sample_shipped": "sample_shipped",
    "sample_sent": "sample_shipped",
    "sent_sample": "sample_shipped",
    "已寄样": "sample_shipped",
    "样品已寄": "sample_shipped",
    "已发样": "sample_shipped",
    "寄样": "sample_shipped",
    "sample_delivered": "sample_delivered",
    "delivered": "sample_delivered",
    "样品签收": "sample_delivered",
    "已签收": "sample_delivered",
    "video_published": "video_published",
    "published": "video_published",
    "视频已发": "video_published",
    "视频已发布": "video_published",
    "已发布视频": "video_published",
    "ad_authorized": "ad_authorized",
    "authorized": "ad_authorized",
    "已授权": "ad_authorized",
    "广告授权": "ad_authorized",
    "ad_running": "ad_running",
    "running": "ad_running",
    "广告投放中": "ad_running",
    "dropped": "dropped",
    "failed": "dropped",
    "cancelled": "dropped",
    "canceled": "dropped",
    "已放弃": "dropped",
    "放弃": "dropped",
}


def _table_exists(conn, table: str) -> bool:
    if engine.dialect.name == "sqlite":
        return bool(
            conn.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"),
                {"table": table},
            ).first()
        )
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table
                """
            ),
            {"table": table},
        ).first()
    )


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    if engine.dialect.name == "sqlite":
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
            """
        ),
        {"table": table},
    )
    return {row[0] for row in rows}


def _department_id(conn, department_code: str | None) -> int | None:
    if not department_code or not _table_exists(conn, "department"):
        return None
    row = conn.execute(
        text("SELECT id FROM department WHERE code = :code LIMIT 1"),
        {"code": department_code},
    ).first()
    return int(row[0]) if row else None


def _scope_where(cols: set[str], department_code: str | None, department_id: int | None) -> str:
    if department_code is None:
        return ""
    if "department_code" in cols:
        if department_code == DEFAULT_DEPARTMENT:
            return " WHERE (department_code = :department_code OR department_code IS NULL OR department_code = '')"
        return " WHERE department_code = :department_code"
    if "department_id" in cols and department_id is not None:
        return " WHERE department_id = :department_id"
    return ""


def _expr(cols: set[str], column: str, alias: str | None = None) -> str:
    name = alias or column
    return f"{column} AS {name}" if column in cols else f"NULL AS {name}"


def _rows_from_table(conn, table: str, department_code: str | None, department_id: int | None) -> list[dict[str, Any]]:
    cols = _columns(conn, table)
    if not cols:
        return []
    wanted = [
        "id",
        "platform",
        "handle",
        "display_name",
        "current_status",
        "owner_bd",
        "store_assigned",
        "bd_owner",
        "category_tags",
        "primary_product_category",
        "recommended_product_type",
        "review_required",
        "review_status",
        "source",
        "created_at",
        "collected_at",
        "last_seen_at",
        "updated_at",
    ]
    sql = (
        "SELECT "
        + ", ".join(_expr(cols, col) for col in wanted)
        + f", '{table}' AS source_table FROM {table}"
        + _scope_where(cols, department_code, department_id)
    )
    return [dict(row) for row in conn.execute(text(sql), {
        "department_code": department_code,
        "department_id": department_id,
    }).mappings().all()]


def _normalize_handle(handle: Any, display_name: Any = None) -> str:
    raw = str(handle or "").strip()
    if not raw and _SIMPLE_HANDLE_RE.match(str(display_name or "").strip()):
        raw = str(display_name or "").strip()
    raw = _HANDLE_RE.sub("", raw).strip().lower()
    return raw


def _normalize_platform(value: Any) -> str:
    text_value = str(value or "tiktok").strip().lower().replace("-", "_")
    if text_value in {"", "unknown"}:
        return "tiktok"
    if text_value in {"tiktok_shop", "shop"}:
        return "tiktok"
    return text_value


def _creator_key(platform: Any, handle: Any, display_name: Any = None) -> tuple[str, str] | None:
    normalized = _normalize_handle(handle, display_name)
    if not normalized:
        return None
    return (_normalize_platform(platform), normalized)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text_value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _json_value(value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return fallback


def _category_from_row(row: dict[str, Any]) -> str | None:
    for key in ("primary_product_category", "recommended_product_type"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    tags = _json_value(row.get("category_tags"), None)
    if isinstance(tags, list):
        for tag in tags:
            text_value = str(tag or "").strip()
            if text_value:
                return text_value
    elif isinstance(tags, str) and tags.strip():
        return tags.strip()
    return None


def _normalize_stage(value: Any) -> str | None:
    text_value = str(value or "").strip()
    if not text_value:
        return None
    text_value = text_value.strip("。.;；,，")
    lower = "_".join(text_value.lower().replace("-", "_").split())
    compact = lower.replace("_", "")
    return (
        _STAGE_ALIASES.get(text_value)
        or _STAGE_ALIASES.get(lower)
        or _STAGE_ALIASES.get(compact)
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "pending"}


def _fact_for(facts: dict[tuple[str, str], dict[str, Any]], key: tuple[str, str], *, platform: Any, handle: Any) -> dict[str, Any]:
    if key not in facts:
        facts[key] = {
            "platform": _normalize_platform(platform),
            "handle": _normalize_handle(handle),
            "stage": "prospect",
            "stage_rank": STAGE_META["prospect"]["rank"],
            "sources": set(),
            "review_pending": False,
            "first_seen": None,
            "last_seen": None,
        }
    return facts[key]


def _merge_stage(fact: dict[str, Any], stage: str | None) -> None:
    if not stage:
        return
    rank = STAGE_META.get(stage, {}).get("rank", 0)
    if rank >= int(fact.get("stage_rank") or 0):
        fact["stage"] = stage
        fact["stage_rank"] = rank


def _merge_date(fact: dict[str, Any], *values: Any) -> None:
    for value in values:
        d = _parse_date(value)
        if d is None:
            continue
        if fact.get("first_seen") is None or d < fact["first_seen"]:
            fact["first_seen"] = d
        if fact.get("last_seen") is None or d > fact["last_seen"]:
            fact["last_seen"] = d


def _merge_fact(
    facts: dict[tuple[str, str], dict[str, Any]],
    row: dict[str, Any],
    *,
    source: str,
    stage: str | None = None,
    review_pending: bool = False,
    category: str | None = None,
    owner: str | None = None,
) -> tuple[str, str] | None:
    key = _creator_key(row.get("platform"), row.get("handle"), row.get("display_name"))
    if key is None:
        return None
    fact = _fact_for(facts, key, platform=row.get("platform"), handle=row.get("handle"))
    fact["sources"].add(source)
    for field in ("display_name",):
        if row.get(field) and not fact.get(field):
            fact[field] = row[field]
    owner_value = owner or row.get("owner_bd") or row.get("bd_owner") or row.get("store_assigned")
    if owner_value and not fact.get("owner"):
        fact["owner"] = str(owner_value).strip()
    category_value = category or _category_from_row(row)
    if category_value and not fact.get("category"):
        fact["category"] = str(category_value).strip()
    _merge_stage(fact, stage or _normalize_stage(row.get("current_status")))
    review_status = str(row.get("review_status") or "").strip().lower()
    if review_pending or _truthy(row.get("review_required")) or review_status in {"pending", "review_pending", "待审核"}:
        fact["review_pending"] = True
    _merge_date(fact, row.get("collected_at"), row.get("created_at"), row.get("last_seen_at"), row.get("updated_at"))
    return key


def _merge_raw_observations(conn, facts: dict[tuple[str, str], dict[str, Any]], department_code: str | None) -> None:
    cols = _columns(conn, "raw_observations")
    if not cols:
        return
    sql = "SELECT platform, source, raw_json, collected_at, created_at FROM raw_observations"
    sql += _scope_where(cols, department_code, None)
    for row in conn.execute(text(sql), {"department_code": department_code, "department_id": None}).mappings().all():
        payload = _json_value(row.get("raw_json"), {}) or {}
        creator = payload.get("creator") if isinstance(payload, dict) else {}
        if not isinstance(creator, dict):
            continue
        shop = payload.get("tiktok_shop") if isinstance(payload, dict) else {}
        list_item = shop.get("list_item") if isinstance(shop, dict) else {}
        import_meta = payload.get("import_meta") if isinstance(payload, dict) else {}
        raw_row = {
            "platform": payload.get("platform") or row.get("platform"),
            "handle": creator.get("handle"),
            "display_name": creator.get("display_name"),
            "current_status": creator.get("current_status") or payload.get("current_status"),
            "owner_bd": creator.get("owner_bd") or creator.get("bd_owner") or payload.get("owner_bd") or payload.get("bd_owner"),
            "created_at": row.get("created_at"),
            "collected_at": row.get("collected_at"),
        }
        category = (
            (list_item or {}).get("category_text")
            or (import_meta or {}).get("category")
            or (import_meta or {}).get("primary_product_category")
        )
        _merge_fact(facts, raw_row, source=f"raw:{row.get('source') or 'observation'}", category=category)


def _merge_outreach(conn, facts: dict[tuple[str, str], dict[str, Any]], department_code: str | None, department_id: int | None) -> None:
    cols = _columns(conn, "outreach")
    creator_cols = _columns(conn, "creator")
    if cols and creator_cols and {"creator_id", "id", "platform", "handle"} <= (cols | creator_cols):
        where = ""
        params = {"department_code": department_code, "department_id": department_id}
        if department_code is not None and "department_id" in cols and department_id is not None:
            where = " WHERE o.department_id = :department_id"
        rows = conn.execute(
            text(
                f"""
                SELECT c.platform, c.handle, c.display_name,
                       o.status, o.action, o.bd_owner, o.store_name,
                       o.video_url, o.ad_auth_code, o.event_date, o.created_at
                FROM outreach o
                JOIN creator c ON c.id = o.creator_id
                {where}
                """
            ),
            params,
        ).mappings().all()
        for row in rows:
            stage_candidates = [
                _normalize_stage(row.get("status")),
                _normalize_stage(row.get("action")),
            ]
            if row.get("video_url"):
                stage_candidates.append("video_published")
            if row.get("ad_auth_code"):
                stage_candidates.append("ad_authorized")
            stage = max(
                (s for s in stage_candidates if s),
                key=lambda s: STAGE_META[s]["rank"],
                default=None,
            )
            _merge_fact(
                facts,
                {
                    "platform": row.get("platform"),
                    "handle": row.get("handle"),
                    "display_name": row.get("display_name"),
                    "created_at": row.get("created_at") or row.get("event_date"),
                },
                source="outreach",
                stage=stage,
                owner=row.get("bd_owner") or row.get("store_name"),
            )

    email_cols = _columns(conn, "outreach_emails")
    lead_cols = _columns(conn, "creators")
    if email_cols and lead_cols and {"creator_id", "status"} <= email_cols:
        where = ""
        params = {"department_code": department_code, "department_id": department_id}
        if department_code is not None and "department_code" in email_cols:
            where = " WHERE e.department_code = :department_code"
        rows = conn.execute(
            text(
                f"""
                SELECT c.platform, c.handle, c.display_name,
                       e.status, e.created_at, e.sent_at, e.created_by
                FROM outreach_emails e
                JOIN creators c ON c.id = e.creator_id
                {where}
                """
            ),
            params,
        ).mappings().all()
        for row in rows:
            status = str(row.get("status") or "").strip().lower()
            if status not in {"queued", "sent"}:
                continue
            _merge_fact(
                facts,
                {
                    "platform": row.get("platform"),
                    "handle": row.get("handle"),
                    "display_name": row.get("display_name"),
                    "created_at": row.get("sent_at") or row.get("created_at"),
                },
                source="outreach_email",
                stage="contacted",
                owner=row.get("created_by"),
            )


def _merge_review_tasks(conn, facts: dict[tuple[str, str], dict[str, Any]], department_code: str | None) -> None:
    review_cols = _columns(conn, "review_tasks")
    lead_cols = _columns(conn, "creators")
    if not review_cols or not lead_cols:
        return
    where = " WHERE r.status = 'pending'"
    if department_code is not None and "department_code" in review_cols:
        where += " AND r.department_code = :department_code"
    rows = conn.execute(
        text(
            f"""
            SELECT c.platform, c.handle, c.display_name, r.created_at
            FROM review_tasks r
            JOIN creators c ON c.id = r.creator_id
            {where}
            """
        ),
        {"department_code": department_code},
    ).mappings().all()
    for row in rows:
        _merge_fact(facts, dict(row), source="review_task", review_pending=True)


def _build_summary(department_code: str | None) -> dict[str, Any]:
    facts: dict[tuple[str, str], dict[str, Any]] = {}
    today = datetime.now().date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    with engine.connect() as conn:
        dept_id = _department_id(conn, department_code)
        for table in ("creator", "tk_creators", "creators"):
            for row in _rows_from_table(conn, table, department_code, dept_id):
                _merge_fact(facts, row, source=table)
        _merge_raw_observations(conn, facts, department_code)
        _merge_outreach(conn, facts, department_code, dept_id)
        _merge_review_tasks(conn, facts, department_code)

    stage_counts = {key: 0 for key in STAGE_ORDER}
    category_counts: Counter[str] = Counter()
    owner_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    trend = {key: 0 for key in day_keys}
    bd: dict[str, dict[str, Any]] = {}

    for fact in facts.values():
        stage = fact.get("stage") or "prospect"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        category_counts[str(fact.get("category") or "未填写").strip() or "未填写"] += 1
        owner = str(fact.get("owner") or "未分配").strip() or "未分配"
        owner_counts[owner] += 1
        for source in fact.get("sources") or []:
            source_counts[str(source)] += 1
        first_seen = fact.get("first_seen")
        if isinstance(first_seen, date) and first_seen.isoformat() in trend:
            trend[first_seen.isoformat()] += 1
        row = bd.setdefault(owner, {
            "owner": owner,
            "creator_count": 0,
            "contacted": 0,
            "confirmed": 0,
            "samples": 0,
            "videos": 0,
            "authorized": 0,
        })
        row["creator_count"] += 1
        rank = STAGE_META.get(stage, {}).get("rank", 0)
        if 20 <= rank < STAGE_META["dropped"]["rank"]:
            row["contacted"] += 1
        if 30 <= rank < STAGE_META["dropped"]["rank"]:
            row["confirmed"] += 1
        if 40 <= rank < STAGE_META["dropped"]["rank"]:
            row["samples"] += 1
        if 60 <= rank < STAGE_META["dropped"]["rank"]:
            row["videos"] += 1
        if 70 <= rank < STAGE_META["dropped"]["rank"]:
            row["authorized"] += 1

    reached_keys = {"contacted", "pending_reply", "confirmed", "sample_shipped", "sample_delivered", "video_published", "ad_authorized", "ad_running"}
    progressed_keys = {"confirmed", "sample_shipped", "sample_delivered", "video_published", "ad_authorized", "ad_running"}

    stage_rows = [
        {"key": key, "name": STAGE_META[key]["label"], "count": stage_counts.get(key, 0)}
        for key in STAGE_ORDER
        if stage_counts.get(key, 0) > 0 or key in {"prospect", "contacted", "confirmed"}
    ]

    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "type": "company" if department_code is None else "department",
            "department_code": department_code,
            "name": "公司全局" if department_code is None else DEPARTMENTS.get(department_code, {}).get("name", department_code),
        },
        "summary": {
            "total_creators": len(facts),
            "today_collected": sum(1 for f in facts.values() if f.get("first_seen") == today),
            "contacted": sum(stage_counts.get(key, 0) for key in reached_keys),
            "review_pending": sum(1 for f in facts.values() if f.get("review_pending")),
            "progressed": sum(stage_counts.get(key, 0) for key in progressed_keys),
        },
        "stage_counts": stage_counts,
        "stage_rows": stage_rows,
        "overview": [
            {"key": key, "name": STAGE_META[key]["label"], "count": stage_counts.get(key, 0)}
            for key in STAGE_ORDER
        ],
        "trend_7d": [{"date": key, "count": trend[key]} for key in day_keys],
        "category_counts": [
            {"name": name, "value": value}
            for name, value in category_counts.most_common(8)
        ],
        "owner_counts": [
            {"name": name, "count": count}
            for name, count in owner_counts.most_common(8)
        ],
        "bd_rows": sorted(bd.values(), key=lambda row: (-row["contacted"], -row["creator_count"], row["owner"]))[:8],
        "source_counts": [
            {"name": name, "count": count}
            for name, count in source_counts.most_common()
        ],
    }


@router.get("/department-summary")
def department_summary(request: Request, _user: dict = Depends(current_user)) -> dict[str, Any]:
    return _build_summary(current_department_code(request))
