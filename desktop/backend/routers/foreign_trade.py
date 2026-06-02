"""Foreign-trade department dashboard + collection statistics.

Aggregates the recruitment lead tables (company_leads / talent_leads) and the
social-media lead tables (xhs_users / xhs_ai_judgments / xhs_extracted_contacts /
xhs_collection_runs) that replace the TikTok-creator pipeline for the foreign
trade department. Empty tables return honest zeros — no fabricated data.

Endpoints (all department-scoped via the request's department_code):
  GET /api/local/foreign-trade/dashboard          → KPI cards + tier / status / source / decision / platform breakdowns + 7d trend
  GET /api/local/foreign-trade/collection         → per-channel stats + paginated recent leads for the collection panels
  GET /api/local/foreign-trade/cleaning/status    → cleaning readiness + backlog
  POST /api/local/foreign-trade/cleaning/run      → deterministic cleaning backfill, optional GPT judge
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models.company_lead import CompanyLead
from ..models.social_lead import (
    XhsAiJudgment,
    XhsCollectionRun,
    XhsExtractedContact,
    XhsUser,
)
from ..models.talent_lead import TalentLead
from ..services.departments import current_department_code, current_user, department_where
from ..services.foreign_trade_cleaning_service import get_cleaning_status, run_cleaning

router = APIRouter(prefix="/api/local/foreign-trade", tags=["foreign-trade"])


# ---- breakdown definitions (order + labels live here so FE & BE agree) ----

TIER_ORDER = ("A", "B", "C", "unrated")
TIER_LABELS = {"A": "A 级", "B": "B 级", "C": "C 级", "unrated": "未评级"}

STATUS_ORDER = ("new", "contacted", "replied", "signed", "dropped")
STATUS_LABELS = {
    "new": "新线索",
    "contacted": "已联系",
    "replied": "已回复",
    "signed": "已签约",
    "dropped": "已放弃",
}

SOURCE_ORDER = ("jobs", "social", "import")
SOURCE_LABELS = {"jobs": "招聘网站", "social": "小红书抖音", "import": "表格导入"}

DECISION_ORDER = ("target_customer", "potential", "irrelevant", "error", "high_priority", "follow_up", "nurture", "ignore")
DECISION_LABELS = {
    "target_customer": "目标客户",
    "potential": "潜在线索",
    "irrelevant": "无关",
    "error": "判定失败",
    "high_priority": "高优先",
    "follow_up": "待跟进",
    "nurture": "培育",
    "ignore": "忽略",
}

PLATFORM_LABELS = {
    "51job": "前程无忧",
    "51job_talent": "前程无忧",
    "zhaopin": "智联招聘",
    "zhaopin_resume": "智联招聘",
    "qzrc": "大泉州人才网",
    "qzrc_job": "大泉州人才网",
    "qzrc_resume": "大泉州人才网",
    "xhs": "小红书",
    "douyin": "抖音",
}

PLATFORM_ALIASES = {
    "51job_talent": "51job",
    "zhaopin_resume": "zhaopin",
    "qzrc_job": "qzrc",
    "qzrc_resume": "qzrc",
}

# Recruitment platforms feed the "jobs" source; table imports use this marker.
IMPORT_SOURCE_TYPES = ("table_import", "csv_import", "xlsx_import")
CHINA_TZ = timezone(timedelta(hours=8))


def _scope(stmt, model, department_code: str | None):
    where = department_where(model, department_code)
    if where is not None:
        stmt = stmt.where(where)
    return stmt


def _count(db: Session, model, department_code: str | None, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    stmt = _scope(stmt, model, department_code)
    for cond in conditions:
        stmt = stmt.where(cond)
    return int(db.scalar(stmt) or 0)


def _group_counts(db: Session, model, column, department_code: str | None) -> dict[str, int]:
    stmt = select(column, func.count()).group_by(column)
    stmt = _scope(stmt, model, department_code)
    out: dict[str, int] = {}
    for value, count in db.execute(stmt).all():
        out[str(value or "").strip()] = int(count or 0)
    return out


def _today() -> date:
    return datetime.now(CHINA_TZ).date()


def _china_day_bounds(day: date) -> tuple[datetime, datetime]:
    start_china = datetime.combine(day, datetime.min.time(), tzinfo=CHINA_TZ)
    end_china = start_china + timedelta(days=1)
    return (
        start_china.astimezone(timezone.utc).replace(tzinfo=None),
        end_china.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _today_count(db: Session, model, department_code: str | None) -> int:
    today = _today()
    start, end = _china_day_bounds(today)
    return _count(
        db, model, department_code,
        model.created_at >= start,
        model.created_at < end,
    )


def _trend_7d(db: Session, models: list[Any], department_code: str | None) -> list[dict[str, Any]]:
    today = _today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    rows: list[dict[str, Any]] = []
    for day in days:
        start, end = _china_day_bounds(date.fromisoformat(day))
        total = 0
        for model in models:
            total += _count(db, model, department_code, model.created_at >= start, model.created_at < end)
        rows.append({"date": day, "count": total})
    return rows


def _rows(order: tuple[str, ...], labels: dict[str, str], counts: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"key": key, "name": labels.get(key, key), "count": int(counts.get(key, 0))}
        for key in order
    ]


def _platform_key(value: str) -> str:
    key = str(value or "").strip()
    return PLATFORM_ALIASES.get(key, key)


@router.get("/dashboard")
def foreign_trade_dashboard(
    request: Request,
    _user: dict = Depends(current_user),
) -> dict[str, Any]:
    department_code = current_department_code(request)
    with SessionLocal() as db:
        return _build_dashboard(db, department_code)


def _build_dashboard(db: Session, department_code: str | None) -> dict[str, Any]:
    # ---- recruitment ----
    company_total = _count(db, CompanyLead, department_code)
    talent_total = _count(db, TalentLead, department_code)
    social_total = _count(db, XhsUser, department_code)

    company_tier = _group_counts(db, CompanyLead, CompanyLead.tier, department_code)
    talent_tier = _group_counts(db, TalentLead, TalentLead.tier, department_code)
    tier_counts = _merge_tier(company_tier, talent_tier)

    company_status = _group_counts(db, CompanyLead, CompanyLead.status, department_code)
    talent_status = _group_counts(db, TalentLead, TalentLead.status, department_code)
    status_counts = {
        key: company_status.get(key, 0) + talent_status.get(key, 0)
        for key in STATUS_ORDER
    }

    company_platform = _group_counts(db, CompanyLead, CompanyLead.platform, department_code)
    talent_platform = _group_counts(db, TalentLead, TalentLead.platform, department_code)
    social_platform = _group_counts(db, XhsUser, XhsUser.platform, department_code)
    platform_counts: dict[str, int] = {}
    for bucket in (company_platform, talent_platform, social_platform):
        for key, count in bucket.items():
            if key:
                platform_key = _platform_key(key)
                platform_counts[platform_key] = platform_counts.get(platform_key, 0) + count

    us_market = _count(db, CompanyLead, department_code, CompanyLead.us_market_flag == 1)
    contacted = sum(status_counts.get(k, 0) for k in ("contacted", "replied", "signed"))

    # ---- social GPT judgments ----
    decision_counts = _group_counts(db, XhsAiJudgment, XhsAiJudgment.decision, department_code)
    high_intent = int(decision_counts.get("target_customer", 0) + decision_counts.get("high_priority", 0))
    social_contacts = _count(db, XhsExtractedContact, department_code)

    source_counts = {
        "jobs": company_total + talent_total,
        "social": social_total,
        "import": _count(
            db, CompanyLead, department_code,
            CompanyLead.source_type.in_(IMPORT_SOURCE_TYPES),
        ) + _count(
            db, TalentLead, department_code,
            TalentLead.source_type.in_(IMPORT_SOURCE_TYPES),
        ),
    }

    today_new = (
        _today_count(db, CompanyLead, department_code)
        + _today_count(db, TalentLead, department_code)
        + _today_count(db, XhsUser, department_code)
    )
    tier_a = int(tier_counts.get("A", 0))

    return {
        "ok": True,
        "generated_at": datetime.now(CHINA_TZ).isoformat(),
        "scope": {"type": "department" if department_code else "company", "department_code": department_code},
        "summary": {
            "total_company_leads": company_total,
            "total_talent_leads": talent_total,
            "total_social_leads": social_total,
            "today_new": today_new,
            "tier_a": tier_a,
            "contacted": contacted,
            "high_intent": high_intent,
            "us_market": us_market,
            "social_contacts": social_contacts,
        },
        "tier_rows": _rows(TIER_ORDER, TIER_LABELS, tier_counts),
        "status_rows": _rows(STATUS_ORDER, STATUS_LABELS, status_counts),
        "source_rows": _rows(SOURCE_ORDER, SOURCE_LABELS, source_counts),
        "decision_rows": _rows(DECISION_ORDER, DECISION_LABELS, decision_counts),
        "platform_rows": sorted(
            ({"name": PLATFORM_LABELS.get(k, k), "value": v} for k, v in platform_counts.items()),
            key=lambda r: r["value"],
            reverse=True,
        ) or [{"name": "未填写", "value": 0}],
        "trend_7d": _trend_7d(db, [CompanyLead, TalentLead, XhsUser], department_code),
    }


def _merge_tier(*buckets: dict[str, int]) -> dict[str, int]:
    out = {key: 0 for key in TIER_ORDER}
    for bucket in buckets:
        for key, count in bucket.items():
            norm = key if key in TIER_ORDER else "unrated"
            out[norm] = out.get(norm, 0) + count
    return out


@router.get("/collection")
def foreign_trade_collection(
    request: Request,
    channel: str = Query(default="jobs"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    department_code = current_department_code(request)
    channel = (channel or "jobs").lower().strip()
    if channel == "social":
        return _social_collection(db, department_code, limit, offset)
    return _jobs_collection(db, department_code, limit, offset)


@router.get("/cleaning/status")
def foreign_trade_cleaning_status(
    request: Request,
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return get_cleaning_status(db, current_department_code(request))


@router.post("/cleaning/run")
def foreign_trade_cleaning_run(
    request: Request,
    body: dict[str, Any] | None = Body(default=None),
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = body or {}
    return run_cleaning(
        db,
        current_department_code(request),
        include_gpt=bool(payload.get("include_gpt")),
        force_gpt=bool(payload.get("force_gpt")),
        gpt_limit=int(payload["gpt_limit"]) if payload.get("gpt_limit") else None,
    )


def _jobs_collection(db: Session, department_code: str | None, limit: int, offset: int) -> dict[str, Any]:
    company_total = _count(db, CompanyLead, department_code)
    talent_total = _count(db, TalentLead, department_code)
    stats = {
        "total": company_total + talent_total,
        "today": _today_count(db, CompanyLead, department_code) + _today_count(db, TalentLead, department_code),
        "company_total": company_total,
        "talent_total": talent_total,
        "tier_a": _count(db, CompanyLead, department_code, CompanyLead.tier == "A")
        + _count(db, TalentLead, department_code, TalentLead.tier == "A"),
        "with_contact": _count(db, CompanyLead, department_code, CompanyLead.contact_email.isnot(None)),
    }
    stmt = _scope(
        select(CompanyLead).order_by(
            func.coalesce(CompanyLead.last_seen_at, CompanyLead.first_seen_at, CompanyLead.created_at).desc()
        ),
        CompanyLead, department_code,
    ).limit(limit).offset(offset)
    items = [
        {
            "id": c.id,
            "kind": "company",
            "name": c.company_name,
            "subtitle": c.industry or c.city or "",
            "platform": c.platform,
            "tier": c.tier,
            "status": c.status,
            "score": c.score,
            "contact": c.contact_email or c.contact_phone or c.hr_wechat or "",
            "us_market": int(c.us_market_flag or 0),
            "created_at": _iso(c.last_seen_at or c.first_seen_at or c.created_at),
        }
        for c in db.scalars(stmt).all()
    ]
    return {"ok": True, "channel": "jobs", "stats": stats, "total": company_total, "items": items}


def _social_collection(db: Session, department_code: str | None, limit: int, offset: int) -> dict[str, Any]:
    user_total = _count(db, XhsUser, department_code)
    stats = {
        "total": user_total,
        "today": _today_count(db, XhsUser, department_code),
        "runs": _count(db, XhsCollectionRun, department_code),
        "with_contact": _count(db, XhsUser, department_code, XhsUser.has_contact == 1),
        "high_intent": _count(
            db,
            XhsAiJudgment,
            department_code,
            XhsAiJudgment.decision.in_(("target_customer", "high_priority")),
        ),
    }
    stmt = _scope(
        select(XhsUser).order_by(
            func.coalesce(XhsUser.last_seen_at, XhsUser.first_seen_at, XhsUser.created_at).desc()
        ),
        XhsUser, department_code,
    ).limit(limit).offset(offset)
    items = [
        {
            "id": u.id,
            "kind": "social",
            "name": u.username_clean or u.account_clean or u.xhs_user_id or "—",
            "subtitle": u.location_text or "",
            "platform": u.platform,
            "followers": u.follower_count,
            "has_contact": int(u.has_contact or 0),
            "profile_url": u.canonical_profile_url,
            "created_at": _iso(u.last_seen_at or u.first_seen_at or u.created_at),
        }
        for u in db.scalars(stmt).all()
    ]
    return {"ok": True, "channel": "social", "stats": stats, "total": user_total, "items": items}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if isinstance(value, datetime):
            value = value.astimezone(CHINA_TZ)
        return value.isoformat()
    return str(value)
