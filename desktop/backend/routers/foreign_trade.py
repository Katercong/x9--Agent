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

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models.company_lead import CompanyLead
from ..models.social_lead import (
    XhsAiJudgment,
    XhsComment,
    XhsCollectionRun,
    XhsExtractedContact,
    XhsNote,
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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_text_list(value: Any, limit: int = 6) -> list[str]:
    text = _text(value)
    if not text:
        return []
    parts: list[str] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            parts = [_text(item) for item in parsed]
        elif isinstance(parsed, dict):
            parts = [_text(v) for v in parsed.values()]
    except (TypeError, ValueError):
        parts = []
    if not parts:
        parts = [p.strip() for p in text.replace("\n", ",").replace("，", ",").split(",")]
    out: list[str] = []
    seen: set[str] = set()
    for item in parts:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _contact_items(*pairs: tuple[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, value in pairs:
        text = _text(value)
        if not text:
            continue
        key = (kind, text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": kind, "value": text})
    return out


def _contact_display(items: list[dict[str, str]]) -> str:
    return " / ".join(item["value"] for item in items[:3])


def _sort_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.min


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
        "with_contact": _count(
            db,
            CompanyLead,
            department_code,
            CompanyLead.contact_email.isnot(None),
        ) + _count(
            db,
            TalentLead,
            department_code,
            TalentLead.contact_email.isnot(None),
        ),
    }
    fetch_limit = max(limit + offset, limit)
    stmt = _scope(
        select(CompanyLead).order_by(
            func.coalesce(CompanyLead.last_seen_at, CompanyLead.first_seen_at, CompanyLead.created_at).desc()
        ),
        CompanyLead, department_code,
    ).limit(fetch_limit)
    talent_stmt = _scope(
        select(TalentLead).order_by(
            func.coalesce(TalentLead.last_seen_at, TalentLead.first_seen_at, TalentLead.created_at).desc()
        ),
        TalentLead, department_code,
    ).limit(fetch_limit)
    items = [_company_item(c) for c in db.scalars(stmt).all()]
    items.extend(_talent_item(t) for t in db.scalars(talent_stmt).all())
    items.sort(key=lambda item: _sort_at(item.pop("_sort_at", None)), reverse=True)
    items = items[offset:offset + limit]
    return {"ok": True, "channel": "jobs", "stats": stats, "total": stats["total"], "items": items}


def _company_item(c: CompanyLead) -> dict[str, Any]:
    collected_at = c.last_seen_at or c.first_seen_at or c.created_at
    contacts = _contact_items(
        ("email", c.contact_email),
        ("phone", c.contact_phone),
        ("wechat", c.hr_wechat),
    )
    return {
        "_sort_at": collected_at,
        "id": c.id,
        "kind": "company",
        "kind_label": "公司客户",
        "name": c.company_name,
        "subtitle": c.industry or c.city or c.company_address or "",
        "platform": c.platform,
        "tier": c.tier,
        "status": c.status,
        "score": c.score,
        "contact": _contact_display(contacts),
        "contacts": contacts,
        "contact_name": c.contact_name,
        "contact_title": c.contact_title,
        "contact_source": c.contact_source,
        "location": " / ".join(x for x in [c.province, c.city] if x),
        "title": c.industry,
        "summary": c.company_description,
        "size_range": c.size_range,
        "source_type": c.source_type,
        "source_mode": c.source_mode,
        "data_quality": c.data_quality,
        "next_action": c.next_action,
        "cooperation_type": c.cooperation_type,
        "score_reason": c.score_reason or c.llm_score_reason,
        "score_suggestion": c.llm_score_suggestion,
        "llm_score_status": c.llm_score_status,
        "tags": _json_text_list(c.lead_tags),
        "keywords": _json_text_list(c.search_keywords) or _json_text_list(c.raw_jd_keywords),
        "raw_titles": _json_text_list(c.raw_jd_titles, limit=4),
        "us_market": int(c.us_market_flag or 0),
        "created_at": _iso(collected_at),
    }


def _talent_item(t: TalentLead) -> dict[str, Any]:
    collected_at = t.last_seen_at or t.first_seen_at or t.created_at
    contacts = _contact_items(
        ("email", t.contact_email),
        ("phone", t.contact_phone),
        ("wechat", t.wechat),
    )
    return {
        "_sort_at": collected_at,
        "id": t.id,
        "kind": "talent",
        "kind_label": "跨境人才",
        "name": t.name_masked or t.desired_title or "未命名人才",
        "subtitle": t.desired_title or t.raw_summary or t.city or "",
        "platform": t.platform,
        "tier": t.tier,
        "status": t.status,
        "score": t.score,
        "contact": _contact_display(contacts),
        "contacts": contacts,
        "location": t.city,
        "title": t.desired_title,
        "summary": t.raw_summary,
        "experience": t.experience,
        "education": t.education,
        "major": t.major,
        "salary_expectation": t.salary_expectation,
        "source_url": t.source_url,
        "resume_download_url": t.resume_download_url,
        "source_type": t.source_type,
        "consent_status": t.consent_status,
        "data_quality": t.data_quality,
        "next_action": t.next_action,
        "cooperation_type": t.cooperation_type,
        "score_reason": t.score_reason or t.llm_score_reason,
        "score_suggestion": t.llm_score_suggestion,
        "llm_score_status": t.llm_score_status,
        "tags": _json_text_list(t.lead_tags),
        "keywords": _json_text_list(t.search_keywords),
        "us_market": 0,
        "created_at": _iso(collected_at),
    }


def _social_collection(db: Session, department_code: str | None, limit: int, offset: int) -> dict[str, Any]:
    user_total = _count(db, XhsUser, department_code)
    stats = {
        "total": user_total,
        "today": _today_count(db, XhsUser, department_code),
        "runs": _count(db, XhsCollectionRun, department_code),
        "with_contact": _count(db, XhsUser, department_code, XhsUser.has_contact == 1),
        "notes": _count(db, XhsNote, department_code),
        "comments": _count(db, XhsComment, department_code),
        "contacts": _count(db, XhsExtractedContact, department_code),
        "judgments": _count(db, XhsAiJudgment, department_code),
        "cleaned": _count(db, XhsUser, department_code, XhsUser.clean_status == "cleaned"),
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
    users = list(db.scalars(stmt).all())
    return {"ok": True, "channel": "social", "stats": stats, "total": user_total, "items": _social_items(db, users)}


def _social_items(db: Session, users: list[XhsUser]) -> list[dict[str, Any]]:
    if not users:
        return []
    user_ids = [u.id for u in users]
    contacts_by_user: dict[str, list[XhsExtractedContact]] = {uid: [] for uid in user_ids}
    for contact in db.scalars(
        select(XhsExtractedContact)
        .where(XhsExtractedContact.user_id.in_(user_ids))
        .order_by(XhsExtractedContact.created_at.desc())
    ).all():
        contacts_by_user.setdefault(contact.user_id or "", []).append(contact)

    note_counts = {
        uid: int(count or 0)
        for uid, count in db.execute(
            select(XhsNote.author_user_id, func.count())
            .where(XhsNote.author_user_id.in_(user_ids))
            .group_by(XhsNote.author_user_id)
        ).all()
    }
    comment_counts = {
        uid: int(count or 0)
        for uid, count in db.execute(
            select(XhsComment.user_id, func.count())
            .where(XhsComment.user_id.in_(user_ids))
            .group_by(XhsComment.user_id)
        ).all()
    }
    judgments: dict[str, XhsAiJudgment] = {}
    for judgment in db.scalars(
        select(XhsAiJudgment)
        .where(XhsAiJudgment.user_id.in_(user_ids))
        .order_by(XhsAiJudgment.user_id, XhsAiJudgment.created_at.desc())
    ).all():
        if judgment.user_id not in judgments:
            judgments[judgment.user_id] = judgment

    items: list[dict[str, Any]] = []
    for u in users:
        collected_at = u.last_seen_at or u.first_seen_at or u.created_at
        contacts = [
            {
                "type": c.contact_type,
                "value": c.value_raw,
                "source": c.source_field,
                "rule": c.rule_code,
            }
            for c in contacts_by_user.get(u.id, [])[:6]
        ]
        j = judgments.get(u.id)
        items.append({
            "id": u.id,
            "kind": "social",
            "kind_label": "社媒博主",
            "name": u.username_clean or u.account_clean or u.xhs_user_id or "未命名博主",
            "subtitle": u.location_text or u.account_clean or "",
            "platform": u.platform,
            "followers": u.follower_count,
            "following": u.following_count,
            "notes_count": note_counts.get(u.id, 0),
            "comments_count": comment_counts.get(u.id, 0),
            "has_contact": int(u.has_contact or 0),
            "contact": _contact_display([{"type": c["type"], "value": c["value"]} for c in contacts]),
            "contacts": contacts,
            "profile_url": u.canonical_profile_url,
            "bio": u.bio_clean,
            "location": u.location_text,
            "clean_status": u.clean_status,
            "contact_signals": _json_text_list(u.contact_signals),
            "platform_signals": _json_text_list(u.platform_signals),
            "fit_score": j.fit_score if j else None,
            "fit_level": j.fit_level if j else None,
            "decision": j.decision if j else None,
            "intent_type": j.intent_type if j else None,
            "judgment": j.judgment if j else None,
            "judged_at": _iso(j.created_at) if j else None,
            "created_at": _iso(collected_at),
        })
    return items


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
