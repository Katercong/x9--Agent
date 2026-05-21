"""V2 dashboard aggregation service.

Provides the data layer for the new `/preview/*` UI (the redesigned
dashboards). Read-only — never writes to the existing tables. All three
creator tables (creators / creator / tk_creators) are preserved as-is;
this module just queries and merges them on the fly.

Key design choices:
 * Unified creator view is computed in Python (not a SQL VIEW or materialized
   view) so we don't touch the production schema. ~900 rows total across
   3 tables — fast enough.
 * Dedup key: ``(lower(trim(platform)), lower(trim(handle)))``. When the
   same creator exists in multiple tables, fields from the highest-priority
   table win (creators > creator > tk_creators), with COALESCE-style fallback.
 * Per-creator "health color" (green / yellow / red) is computed inline,
   based on days-since-last-contact + recommendation score + email
   availability. No new DB column — entirely derived.
 * Aggregates use SQL COUNT/aggregation where possible. We never load
   raw_observations.raw_json into memory (this is what caused the 17 GB
   blow-up we just fixed).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


# Status normalization (matches dashboard.py STAGE_META). These are the
# 7 stages of the main pipeline funnel.
STAGE_ORDER = [
    "prospect",         # 潜在线索
    "contacted",        # 已联系
    "pending_reply",    # 待回复
    "confirmed",        # 已确认
    "sample_shipped",   # 已寄样
    "sample_delivered", # 样品签收
    "video_published",  # 视频已发
    "ad_authorized",    # 已授权
    "ad_running",       # 广告投放中
    "dropped",          # 已放弃
]
STAGE_LABEL = {
    "prospect": "潜在线索",
    "contacted": "已联系",
    "pending_reply": "待回复",
    "confirmed": "已确认",
    "sample_shipped": "已寄样",
    "sample_delivered": "样品签收",
    "video_published": "视频已发",
    "ad_authorized": "已授权",
    "ad_running": "广告投放中",
    "dropped": "已放弃",
}
PIPELINE_FUNNEL_STAGES = [
    "prospect", "contacted", "confirmed",
    "sample_shipped", "video_published", "ad_authorized",
]

_STATUS_ALIASES = {
    # CN
    "待建联": "prospect", "未建联": "prospect", "潜在线索": "prospect",
    "已建联": "contacted", "已联系": "contacted",
    "待回复": "pending_reply", "等待回复": "pending_reply",
    "已确认": "confirmed", "确认合作": "confirmed",
    "已寄样": "sample_shipped", "已发样": "sample_shipped",
    "样品签收": "sample_delivered", "已签收": "sample_delivered",
    "视频已发": "video_published", "视频已发布": "video_published",
    "已授权": "ad_authorized", "广告授权": "ad_authorized",
    "广告投放中": "ad_running", "投放中": "ad_running",
    "已放弃": "dropped", "放弃": "dropped",
    # EN (already-normalized values)
    **{s: s for s in STAGE_ORDER},
}


def _norm_stage(value: Any) -> str | None:
    if not value:
        return None
    text_value = str(value).strip()
    return _STATUS_ALIASES.get(text_value) or _STATUS_ALIASES.get(text_value.lower())


# ---------------------------------------------------------------------------
# Unified creator query
# ---------------------------------------------------------------------------

# Columns we project from each source table. Field name -> SQL expression.
# Tables don't all have the same columns; missing columns become NULL.
_BASE_COLUMNS = [
    "platform", "handle", "display_name", "followers_count",
    "email", "current_status", "owner_bd", "store_assigned",
    "department_code", "primary_product_category", "fit_level",
    "queue_type", "recommendation_score", "avatar_url",
    "tier", "country", "language", "gmv_30d_usd",
    "collected_at", "last_seen_at", "updated_at", "last_contact_date",
    "notes", "bio",
]


def _columns_of(conn, table: str) -> dict[str, str]:
    """Return {column_name: data_type} for a table. Empty dict if missing."""
    rows = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": table},
    ).all()
    return {r[0]: r[1] for r in rows}


_DATE_LIKE_COLS = {
    "collected_at", "last_seen_at", "updated_at", "created_at",
    "last_contact_date", "first_contact_date",
}


def _select_expr(cols: dict[str, str], name: str, alias: str | None = None) -> str:
    """Produce a uniform SQL expression for `name`, regardless of source type.

    Tables disagree on storage: ``creators`` uses real ``timestamp without time
    zone``, while legacy ``creator`` / ``tk_creators`` store dates as TEXT
    (with stray empty strings). We normalize everything to TEXT in the SELECT
    so the union types align and PG never tries to cast '' → timestamp."""
    alias = alias or name
    # Special-case legacy field rename.
    if name == "followers_count" and name not in cols and "followers" in cols:
        return f"followers::bigint AS {alias}"
    if name not in cols:
        return f"NULL AS {alias}"

    dtype = (cols.get(name) or "").lower()
    # Date-ish columns → unify to TEXT (caller parses via _to_date).
    if name in _DATE_LIKE_COLS:
        if "timestamp" in dtype or "date" in dtype:
            return f"to_char({name}, 'YYYY-MM-DD\"T\"HH24:MI:SS') AS {alias}"
        return f"NULLIF({name}, '') AS {alias}"
    return f"{name} AS {alias}"


def _build_table_select(conn, table: str) -> str | None:
    cols = _columns_of(conn, table)
    if not cols or "handle" not in cols or "platform" not in cols:
        return None
    parts = [f"'{table}'::text AS source_table"]
    for c in _BASE_COLUMNS:
        parts.append(_select_expr(cols, c))
    return f"SELECT {', '.join(parts)} FROM {table}"


def fetch_unified_creators(db: Session) -> list[dict[str, Any]]:
    """Return one row per (platform, handle) merged across the three tables.

    Field precedence: creators > creator > tk_creators (i.e. modern table
    wins; falls back to legacy tables for missing fields like tier/country/
    gmv that only exist on `creator`).
    """
    selects = []
    raw_conn = db.connection()
    for table in ("creators", "creator", "tk_creators"):
        sub = _build_table_select(raw_conn, table)
        if sub:
            selects.append(sub)
    if not selects:
        return []

    union_sql = " UNION ALL ".join(f"({s})" for s in selects)
    full_sql = f"SELECT * FROM ({union_sql}) AS u"

    # Stream the union — ~900 rows but be safe.
    result = raw_conn.execution_options(yield_per=500).execute(text(full_sql))

    # Group by (platform, handle_key), merge with priority.
    priority = {"creators": 0, "creator": 1, "tk_creators": 2}
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in result.mappings():
        platform = (row.get("platform") or "tiktok").strip().lower()
        handle = (row.get("handle") or "").strip().lstrip("@").lower()
        if not handle:
            continue
        key = (platform, handle)
        cur = merged.get(key)
        if cur is None:
            cur = dict(row)
            cur["platform"] = platform
            cur["handle_key"] = handle
            merged[key] = cur
            continue
        # Same creator from a different table — fill in any NULL fields
        # from this row, but only if our current source is lower-priority
        # OR our current value is NULL.
        cur_p = priority.get(cur.get("source_table"), 9)
        new_p = priority.get(row.get("source_table"), 9)
        for k, v in row.items():
            if v in (None, "", 0):
                continue
            if cur.get(k) in (None, "", 0) or new_p < cur_p:
                cur[k] = v
        if new_p < cur_p:
            cur["source_table"] = row.get("source_table")
    return list(merged.values())


# ---------------------------------------------------------------------------
# Health color
# ---------------------------------------------------------------------------

def compute_health(creator: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Derive a green/yellow/red health signal per creator.

    Rules (tunable):
      * 🔴 red:   no email AND no contact in 14d AND recommended
      * 🟡 yellow: contacted but no movement in 7d
      * 🟢 green:  recently contacted OR not yet due
      * ⚪ grey:   not applicable (e.g. dropped, no owner)
    """
    today = today or datetime.now().date()
    stage = _norm_stage(creator.get("current_status")) or "prospect"
    if stage == "dropped":
        return {"color": "grey", "reason": "已放弃"}

    last_contact_raw = creator.get("last_contact_date")
    last_contact: date | None
    if isinstance(last_contact_raw, datetime):
        last_contact = last_contact_raw.date()
    elif isinstance(last_contact_raw, date):
        last_contact = last_contact_raw
    else:
        last_contact = None

    has_email = bool(creator.get("email"))
    rec_score = int(creator.get("recommendation_score") or 0)

    if stage in {"prospect", "contacted"} and last_contact is None and rec_score >= 60:
        if not has_email:
            return {"color": "red", "reason": "推荐分高但无邮箱且从未联系"}
        return {"color": "red", "reason": "推荐达人但从未联系"}

    if last_contact is None:
        return {"color": "grey", "reason": "无联系记录"}

    days = (today - last_contact).days
    if stage in {"contacted", "pending_reply"} and days > 7:
        return {"color": "yellow", "reason": f"已联系 {days} 天无推进"}
    if stage == "sample_shipped" and days > 14:
        return {"color": "yellow", "reason": f"寄样 {days} 天未签收"}
    if days > 30 and stage not in {"video_published", "ad_running", "ad_authorized"}:
        return {"color": "red", "reason": f"{days} 天无活动"}
    return {"color": "green", "reason": "活跃中"}


# ---------------------------------------------------------------------------
# Pulse aggregation (北极星总览)
# ---------------------------------------------------------------------------

def _date_range(range_key: str) -> tuple[date, date]:
    today = datetime.now().date()
    if range_key == "today":
        return today, today
    if range_key == "week":
        return today - timedelta(days=6), today
    if range_key == "month":
        return today - timedelta(days=29), today
    return today - timedelta(days=6), today  # default = week


def get_pulse(db: Session, range_key: str = "week") -> dict[str, Any]:
    """Company-level pulse: north-star KPIs + funnel + by-department + alerts.

    Designed for the new `/preview/pulse` page. Single endpoint returns
    everything that page needs."""
    today = datetime.now().date()
    start, end = _date_range(range_key)

    creators = fetch_unified_creators(db)
    n_total = len(creators)

    # North-star: today + previous-period delta
    today_creators = sum(
        1 for c in creators
        if _to_date(c.get("collected_at") or c.get("created_at")) == today
    )
    yesterday = today - timedelta(days=1)
    yest_creators = sum(
        1 for c in creators
        if _to_date(c.get("collected_at") or c.get("created_at")) == yesterday
    )

    # Stage funnel (from current_status)
    stage_counts: Counter = Counter()
    for c in creators:
        st = _norm_stage(c.get("current_status"))
        if st:
            stage_counts[st] += 1
    funnel = [
        {"stage": s, "label": STAGE_LABEL[s], "count": stage_counts.get(s, 0)}
        for s in PIPELINE_FUNNEL_STAGES
    ]

    # Outreach stats from outreach_emails table
    sent_today, sent_period = _outreach_sent_counts(db, start, today, end)

    # By-department breakdown
    dept_rows = _department_breakdown(creators, today)

    # Alerts
    alerts = _build_alerts(db, creators, today)

    return {
        "ok": True,
        "range": range_key,
        "generated_at": datetime.now().isoformat(),
        "north_star": [
            {
                "key": "today_collected",
                "label": "今日采集",
                "value": today_creators,
                "delta_pct": _delta_pct(today_creators, yest_creators),
                "compare_label": "vs 昨日",
            },
            {
                "key": "period_outreach",
                "label": f"{_range_cn(range_key)}已建联",
                "value": sent_period,
                "delta_pct": None,
                "compare_label": "封邮件",
            },
            {
                "key": "creator_pool",
                "label": "达人池规模",
                "value": n_total,
                "delta_pct": None,
                "compare_label": "三源去重",
            },
        ],
        "funnel": funnel,
        "departments": dept_rows,
        "alerts": alerts,
    }


def _outreach_sent_counts(db: Session, start: date, today: date, end: date) -> tuple[int, int]:
    sql = text(
        "SELECT "
        " SUM(CASE WHEN DATE(COALESCE(sent_at, created_at)) = :today THEN 1 ELSE 0 END) AS today_n,"
        " SUM(CASE WHEN DATE(COALESCE(sent_at, created_at)) BETWEEN :start AND :end THEN 1 ELSE 0 END) AS period_n "
        "FROM outreach_emails WHERE status IN ('sent','delivered')"
    )
    try:
        row = db.execute(sql, {"today": today, "start": start, "end": end}).first()
        return int(row[0] or 0), int(row[1] or 0)
    except Exception:
        return 0, 0


def _department_breakdown(creators: list[dict], today: date) -> list[dict]:
    by_dept: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "creator_count": 0,
        "today_collected": 0,
        "contacted": 0,
        "video_published": 0,
        "by_day_7": [0] * 7,
    })
    seven_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    day_index = {d: i for i, d in enumerate(seven_days)}
    for c in creators:
        dept = c.get("department_code") or "未分配"
        bucket = by_dept[dept]
        bucket["creator_count"] += 1
        d = _to_date(c.get("collected_at") or c.get("created_at"))
        if d == today:
            bucket["today_collected"] += 1
        if d in day_index:
            bucket["by_day_7"][day_index[d]] += 1
        stage = _norm_stage(c.get("current_status"))
        if stage in {"contacted", "pending_reply", "confirmed", "sample_shipped"}:
            bucket["contacted"] += 1
        if stage in {"video_published", "ad_authorized", "ad_running"}:
            bucket["video_published"] += 1
    return [
        {"department_code": code, **values, "health": _dept_health(values)}
        for code, values in sorted(by_dept.items(), key=lambda kv: -kv[1]["creator_count"])
    ]


def _dept_health(values: dict[str, Any]) -> str:
    if values["creator_count"] == 0:
        return "grey"
    contact_rate = values["contacted"] / values["creator_count"]
    if contact_rate >= 0.4:
        return "green"
    if contact_rate >= 0.2:
        return "yellow"
    return "red"


def _build_alerts(db: Session, creators: list[dict], today: date) -> list[dict]:
    alerts: list[dict] = []
    # 1. Overdue creators (recommended, no contact in 14d)
    overdue = sum(
        1 for c in creators
        if int(c.get("recommendation_score") or 0) >= 60
        and c.get("last_contact_date") is None
        and _norm_stage(c.get("current_status")) in {"prospect", None}
    )
    if overdue:
        alerts.append({
            "severity": "yellow",
            "label": "推荐达人未联系",
            "count": overdue,
            "action": "/preview/creators?tab=pool",
        })
    # 2. Outreach failures (last 7d)
    try:
        n_failed = db.execute(
            text("SELECT COUNT(*) FROM outreach_emails WHERE status='failed' AND created_at >= :since"),
            {"since": today - timedelta(days=7)},
        ).scalar() or 0
        if n_failed:
            alerts.append({
                "severity": "red",
                "label": "近 7 天邮件发送失败",
                "count": int(n_failed),
                "action": "/preview/creators?has_failed_email=1",
            })
    except Exception:
        pass
    # 3. Pending approval users
    try:
        n_pending = db.execute(
            text("SELECT COUNT(*) FROM app_users WHERE approval_status='pending'")
        ).scalar() or 0
        if n_pending:
            alerts.append({
                "severity": "yellow",
                "label": "待审核注册申请",
                "count": int(n_pending),
                "action": "/a/users",
            })
    except Exception:
        pass
    # 4. 5xx errors in last hour
    try:
        n_5xx = db.execute(
            text("SELECT COUNT(*) FROM request_logs WHERE status_code >= 500 AND ts >= :since"),
            {"since": datetime.utcnow() - timedelta(hours=1)},
        ).scalar() or 0
        if n_5xx > 5:
            alerts.append({
                "severity": "red",
                "label": "近 1 小时 5xx 错误",
                "count": int(n_5xx),
                "action": "/system/health",
            })
    except Exception:
        pass
    return alerts


# ---------------------------------------------------------------------------
# /me — personal workspace
# ---------------------------------------------------------------------------

def get_me(db: Session, user: dict[str, Any] | None) -> dict[str, Any]:
    """Personal workspace data: north-star + priority queues + sparkline."""
    if not user:
        return {"ok": False, "detail": "login required"}
    today = datetime.now().date()
    creators = fetch_unified_creators(db)
    aliases = _user_aliases(user)
    mine = [c for c in creators if _matches_alias(c.get("owner_bd"), aliases)]

    # KPIs: week counts
    week_start = today - timedelta(days=6)
    weekly = {
        "contacted": 0,
        "sample_shipped": 0,
        "video_published": 0,
        "deal_closed": 0,
    }
    for c in mine:
        d = _to_date(c.get("last_contact_date")) or _to_date(c.get("updated_at"))
        if d and d >= week_start:
            stage = _norm_stage(c.get("current_status"))
            if stage in {"contacted", "pending_reply"}:
                weekly["contacted"] += 1
            elif stage in {"sample_shipped", "sample_delivered"}:
                weekly["sample_shipped"] += 1
            elif stage in {"video_published", "ad_authorized", "ad_running"}:
                weekly["video_published"] += 1

    # Priority queues
    queues = _build_priority_queues(mine, today)

    # 7-day sparkline of my activity
    spark = _personal_sparkline(mine, today)

    # Personal funnel vs dept average
    funnel = _personal_funnel(mine, creators, user)

    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "user": {
            "id": user.get("id"),
            "display_name": user.get("display_name") or user.get("username"),
            "role": user.get("role"),
            "department_code": user.get("department_code"),
        },
        "owned_count": len(mine),
        "weekly": weekly,
        "queues": queues,
        "sparkline_7d": spark,
        "personal_funnel": funnel,
    }


def _build_priority_queues(mine: list[dict], today: date) -> dict[str, list[dict]]:
    must_today: list[dict] = []
    follow_up: list[dict] = []
    sample_log: list[dict] = []
    for c in mine:
        stage = _norm_stage(c.get("current_status")) or "prospect"
        last = _to_date(c.get("last_contact_date"))
        rec_score = int(c.get("recommendation_score") or 0)

        if stage in {"prospect"} and last is None and rec_score >= 60:
            must_today.append(_compact_creator(c, reason="推荐分高,未联系"))
        elif stage == "contacted" and last and (today - last).days >= 5:
            follow_up.append(_compact_creator(c, reason=f"已联系 {(today-last).days} 天无回复"))
        elif stage == "sample_shipped":
            sample_log.append(_compact_creator(c, reason="样品已寄,待签收/物流登记"))
    return {
        "must_today": sorted(must_today, key=lambda x: -x["recommendation_score"])[:20],
        "follow_up": sorted(follow_up, key=lambda x: -x["recommendation_score"])[:20],
        "sample_log": sample_log[:20],
    }


def _personal_sparkline(mine: list[dict], today: date) -> list[dict]:
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    out = []
    for d in days:
        out.append({
            "date": d.isoformat(),
            "collected": sum(1 for c in mine if _to_date(c.get("collected_at") or c.get("created_at")) == d),
            "contacted": sum(1 for c in mine if _to_date(c.get("last_contact_date")) == d),
        })
    return out


def _personal_funnel(mine: list[dict], all_creators: list[dict], user: dict) -> list[dict]:
    dept_peers = []
    user_dept = user.get("department_code")
    if user_dept:
        dept_peers = [c for c in all_creators if c.get("department_code") == user_dept]
    out = []
    for stage in PIPELINE_FUNNEL_STAGES:
        mine_n = sum(1 for c in mine if _norm_stage(c.get("current_status")) == stage)
        peers_n = sum(1 for c in dept_peers if _norm_stage(c.get("current_status")) == stage) if dept_peers else 0
        out.append({
            "stage": stage,
            "label": STAGE_LABEL[stage],
            "mine": mine_n,
            "department": peers_n,
        })
    return out


# ---------------------------------------------------------------------------
# /creators — unified list with filters & tabs
# ---------------------------------------------------------------------------

def get_creators_unified(
    db: Session,
    *,
    tab: str = "all",
    q: str | None = None,
    platform: str | None = None,
    tier: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    limit: int = 200,
    offset: int = 0,
    user: dict | None = None,
) -> dict[str, Any]:
    all_creators = fetch_unified_creators(db)
    today = datetime.now().date()
    aliases = _user_aliases(user) if user else set()

    # Filtering
    def keep(c: dict) -> bool:
        if q:
            q_lower = q.lower()
            haystack = " ".join(filter(None, [
                str(c.get("handle") or ""),
                str(c.get("display_name") or ""),
                str(c.get("email") or ""),
                str(c.get("notes") or ""),
            ])).lower()
            if q_lower not in haystack:
                return False
        if platform and (c.get("platform") or "").lower() != platform.lower():
            return False
        if tier and (c.get("tier") or "") != tier:
            return False
        if status:
            stage = _norm_stage(c.get("current_status"))
            if stage != status:
                return False
        if owner and (c.get("owner_bd") or "") != owner:
            return False
        # Tab routing
        if tab == "mine":
            return _matches_alias(c.get("owner_bd"), aliases)
        if tab == "pool":
            return not c.get("owner_bd")
        if tab == "pending":
            return _norm_stage(c.get("current_status")) in {"prospect", None}
        if tab == "contacted":
            return _norm_stage(c.get("current_status")) in {
                "contacted", "pending_reply", "confirmed",
                "sample_shipped", "sample_delivered",
            }
        if tab == "active":
            return _norm_stage(c.get("current_status")) in {
                "video_published", "ad_authorized", "ad_running",
            }
        return True

    filtered = [c for c in all_creators if keep(c)]

    # KPIs (filter-aware)
    avg_score = (sum(int(c.get("recommendation_score") or 0) for c in filtered) / len(filtered)) if filtered else 0
    contacted = sum(
        1 for c in filtered
        if _norm_stage(c.get("current_status")) not in {None, "prospect", "dropped"}
    )
    contact_rate = (contacted / len(filtered) * 100) if filtered else 0

    # Decorate each row with health color, then paginate.
    items = []
    for c in filtered[offset:offset + limit]:
        health = compute_health(c, today)
        items.append({
            "platform": c.get("platform"),
            "handle": c.get("handle"),
            "handle_key": c.get("handle_key"),
            "display_name": c.get("display_name"),
            "avatar_url": c.get("avatar_url"),
            "followers_count": c.get("followers_count"),
            "email": c.get("email"),
            "tier": c.get("tier"),
            "country": c.get("country"),
            "gmv_30d_usd": c.get("gmv_30d_usd"),
            "recommendation_score": c.get("recommendation_score"),
            "primary_product_category": c.get("primary_product_category"),
            "current_status": c.get("current_status"),
            "stage": _norm_stage(c.get("current_status")),
            "stage_label": STAGE_LABEL.get(_norm_stage(c.get("current_status")) or "", ""),
            "owner_bd": c.get("owner_bd"),
            "department_code": c.get("department_code"),
            "last_contact_date": _as_iso(c.get("last_contact_date")),
            "collected_at": _as_iso(c.get("collected_at")),
            "source_table": c.get("source_table"),
            "health": health,
        })

    return {
        "ok": True,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "summary": {
            "filtered_count": len(filtered),
            "avg_recommendation_score": round(avg_score, 1),
            "contact_rate_pct": round(contact_rate, 1),
            "with_email": sum(1 for c in filtered if c.get("email")),
            "with_owner": sum(1 for c in filtered if c.get("owner_bd")),
        },
        "items": items,
    }


# ---------------------------------------------------------------------------
# /creators/:id 360°
# ---------------------------------------------------------------------------

def get_creator_360(db: Session, platform: str, handle: str) -> dict[str, Any]:
    """Per-creator full profile: basics + timeline + emails + recommendation."""
    creators = fetch_unified_creators(db)
    key = (platform.lower(), handle.lower().lstrip("@"))
    found = next((c for c in creators if (c["platform"], c["handle_key"]) == key), None)
    if not found:
        return {"ok": False, "detail": "creator not found"}

    today = datetime.now().date()
    health = compute_health(found, today)

    # Email history
    emails = _email_history(db, found)

    # Timeline events
    timeline = _timeline_events(found, emails)

    # Raw observations count
    obs_count = _observation_count(db, found.get("platform"), found.get("handle_key"))

    return {
        "ok": True,
        "creator": {
            "platform": found.get("platform"),
            "handle": found.get("handle"),
            "handle_key": found.get("handle_key"),
            "display_name": found.get("display_name"),
            "avatar_url": found.get("avatar_url"),
            "bio": found.get("bio"),
            "followers_count": found.get("followers_count"),
            "email": found.get("email"),
            "tier": found.get("tier"),
            "country": found.get("country"),
            "language": found.get("language"),
            "gmv_30d_usd": found.get("gmv_30d_usd"),
            "primary_product_category": found.get("primary_product_category"),
            "recommendation_score": found.get("recommendation_score"),
            "current_status": found.get("current_status"),
            "stage": _norm_stage(found.get("current_status")),
            "stage_label": STAGE_LABEL.get(_norm_stage(found.get("current_status")) or "", ""),
            "owner_bd": found.get("owner_bd"),
            "store_assigned": found.get("store_assigned"),
            "department_code": found.get("department_code"),
            "queue_type": found.get("queue_type"),
            "fit_level": found.get("fit_level"),
            "notes": found.get("notes"),
            "source_table": found.get("source_table"),
            "collected_at": _as_iso(found.get("collected_at")),
            "last_contact_date": _as_iso(found.get("last_contact_date")),
            "last_seen_at": _as_iso(found.get("last_seen_at")),
            "updated_at": _as_iso(found.get("updated_at")),
        },
        "health": health,
        "emails": emails,
        "timeline": timeline,
        "observation_count": obs_count,
    }


def _email_history(db: Session, creator: dict) -> list[dict]:
    try:
        # outreach_emails.creator_id may match either the new id or legacy id;
        # we match on creator handle through creators table for robustness.
        creator_ids: list[str] = []
        if creator.get("source_table") == "creators":
            # we don't have id field in unified row directly; query by handle
            pass
        # Simpler: join via lower(handle) on `creators` table to get id.
        result = db.execute(
            text(
                "SELECT e.id, e.subject, e.status, e.to_email, e.from_email, "
                "       e.sent_at, e.created_at, e.gmail_thread_id "
                "FROM outreach_emails e "
                "JOIN creators c ON c.id = e.creator_id "
                "WHERE lower(c.handle) = :h AND lower(c.platform) = :p "
                "ORDER BY e.created_at DESC LIMIT 50"
            ),
            {"h": creator.get("handle_key"), "p": creator.get("platform")},
        )
        return [
            {
                "id": row[0], "subject": row[1], "status": row[2],
                "to_email": row[3], "from_email": row[4],
                "sent_at": _as_iso(row[5]), "created_at": _as_iso(row[6]),
                "has_reply": row[7] is not None,
            }
            for row in result.all()
        ]
    except Exception:
        return []


def _observation_count(db: Session, platform: str, handle_key: str) -> int:
    try:
        # raw_observations doesn't have a normalized handle column.
        # Use a LIKE on raw_json — slow but bounded, and we read no rows.
        sql = text(
            "SELECT COUNT(*) FROM raw_observations "
            "WHERE platform = :p AND raw_json LIKE :pat"
        )
        result = db.execute(sql, {
            "p": platform,
            "pat": f'%"handle": "{handle_key}"%',
        }).scalar()
        return int(result or 0)
    except Exception:
        return 0


def _timeline_events(creator: dict, emails: list[dict]) -> list[dict]:
    events: list[dict] = []
    if creator.get("collected_at"):
        events.append({
            "ts": _as_iso(creator.get("collected_at")),
            "kind": "collected",
            "label": "首次采集",
        })
    if creator.get("last_seen_at"):
        events.append({
            "ts": _as_iso(creator.get("last_seen_at")),
            "kind": "seen",
            "label": "最近采集到",
        })
    for e in emails[:20]:
        events.append({
            "ts": e.get("sent_at") or e.get("created_at"),
            "kind": f"email_{e.get('status')}",
            "label": f"邮件 {e.get('status')}: {e.get('subject')}",
        })
    return sorted([e for e in events if e["ts"]], key=lambda x: x["ts"], reverse=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_date(value: Any) -> date | None:
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


def _as_iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _delta_pct(now: int, prev: int) -> float | None:
    if prev == 0:
        return None
    return round((now - prev) / prev * 100, 1)


def _range_cn(range_key: str) -> str:
    return {"today": "今日", "week": "本周", "month": "本月"}.get(range_key, "本周")


def _user_aliases(user: dict[str, Any]) -> set[str]:
    values = {
        user.get("id"), user.get("username"), user.get("display_name"),
        user.get("identity"), user.get("email"),
    }
    for v in (user.get("email"), user.get("identity")):
        if v and "@" in str(v):
            values.add(str(v).split("@", 1)[0])
    return {str(v).strip().lower() for v in values if v}


def _matches_alias(value: Any, aliases: set[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in aliases


def _compact_creator(c: dict, *, reason: str) -> dict:
    return {
        "handle": c.get("handle"),
        "handle_key": c.get("handle_key"),
        "platform": c.get("platform"),
        "display_name": c.get("display_name"),
        "followers_count": c.get("followers_count"),
        "recommendation_score": int(c.get("recommendation_score") or 0),
        "current_status": c.get("current_status"),
        "stage_label": STAGE_LABEL.get(_norm_stage(c.get("current_status")) or "", ""),
        "reason": reason,
    }
