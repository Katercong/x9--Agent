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
    XhsNoteMedia,
    XhsNote,
    XhsUserHistoryPost,
    XhsUserSource,
    XhsUser,
)
from ..models.talent_lead import TalentLead
from ..services.departments import current_department_code, current_user, department_where
from ..services.foreign_trade_cleaning_service import get_cleaning_status, run_cleaning
from ..services.xhs_lead_service import PROMPT_VERSION
from ..utils.foreign_trade_scoring_scheduler import request_auto_score

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

DECISION_ORDER = (
    "target_customer",
    "experienced_seller",
    "logistics_partner",
    "supplier_peer",
    "potential",
    "irrelevant",
    "error",
    "high_priority",
    "follow_up",
    "nurture",
    "ignore",
)
DECISION_LABELS = {
    "target_customer": "目标客户",
    "experienced_seller": "经验卖家",
    "logistics_partner": "物流伙伴",
    "supplier_peer": "供应方同行",
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


def _current_judgment_decision_counts(db: Session, department_code: str | None) -> dict[str, int]:
    stmt = select(XhsAiJudgment.decision, func.count()).where(XhsAiJudgment.prompt_version == PROMPT_VERSION).group_by(XhsAiJudgment.decision)
    stmt = _scope(stmt, XhsAiJudgment, department_code)
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
    labels = {"xhs_handle": "小红书号", "douyin_handle": "抖音号"}
    parts: list[str] = []
    for item in items[:3]:
        value = item.get("value")
        if not value:
            continue
        label = labels.get(item.get("type") or "")
        parts.append(f"{label}: {value}" if label else value)
    return " / ".join(parts)


def _social_contact_type(contact: XhsExtractedContact) -> str:
    contact_type = contact.contact_type or ""
    if contact_type in {"xhs_handle", "douyin_handle"}:
        return contact_type
    if contact_type == "platform_handle":
        rule = (contact.rule_code or "").lower()
        if rule.startswith("douyin"):
            return "douyin_handle"
        return "xhs_handle"
    return contact_type


def _social_contact_label(contact_type: str) -> str | None:
    return {"xhs_handle": "小红书号", "douyin_handle": "抖音号"}.get(contact_type)


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
    decision_counts = _current_judgment_decision_counts(db, department_code)
    high_intent = int(
        decision_counts.get("target_customer", 0)
        + decision_counts.get("experienced_seller", 0)
        + decision_counts.get("high_priority", 0)
    )
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
    department_code = current_department_code(request)
    status = get_cleaning_status(db, department_code)
    summary = status.get("summary") or {}
    if summary.get("openai_configured") and int(summary.get("unjudged_with_contact") or 0) > 0:
        request_auto_score(department_code)
    return status


@router.post("/cleaning/run")
def foreign_trade_cleaning_run(
    request: Request,
    body: dict[str, Any] | None = Body(default=None),
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    payload = body or {}
    include_gpt = payload.get("include_gpt")
    if include_gpt is None:
        include_gpt = True
    return run_cleaning(
        db,
        current_department_code(request),
        include_gpt=bool(include_gpt),
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
        "media": _count(db, XhsNoteMedia, department_code),
        "sources": _count(db, XhsUserSource, department_code),
        "history_posts": _count(db, XhsUserHistoryPost, department_code),
        "contacts": _count(db, XhsExtractedContact, department_code),
        "judgments": _count(db, XhsAiJudgment, department_code, XhsAiJudgment.prompt_version == PROMPT_VERSION),
        "cleaned": _count(db, XhsUser, department_code, XhsUser.clean_status == "cleaned"),
        "high_intent": _count(
            db,
            XhsAiJudgment,
            department_code,
            XhsAiJudgment.prompt_version == PROMPT_VERSION,
            XhsAiJudgment.decision.in_(("target_customer", "experienced_seller", "high_priority")),
        ),
    }
    stmt = _scope(
        select(XhsUser).order_by(
            func.coalesce(XhsUser.last_seen_at, XhsUser.first_seen_at, XhsUser.created_at).desc()
        ),
        XhsUser, department_code,
    ).limit(limit).offset(offset)
    users = list(db.scalars(stmt).all())
    return {"ok": True, "channel": "social", "stats": stats, "total": user_total, "items": _social_items_complete(db, users)}


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
        .where(XhsAiJudgment.user_id.in_(user_ids), XhsAiJudgment.prompt_version == PROMPT_VERSION)
        .order_by(XhsAiJudgment.user_id, XhsAiJudgment.created_at.desc())
    ).all():
        if judgment.user_id not in judgments:
            judgments[judgment.user_id] = judgment

    items: list[dict[str, Any]] = []
    for u in users:
        collected_at = u.last_seen_at or u.first_seen_at or u.created_at
        contacts = []
        for c in contacts_by_user.get(u.id, [])[:6]:
            contact_type = _social_contact_type(c)
            contacts.append({
                "type": contact_type,
                "label": _social_contact_label(contact_type),
                "value": c.value_raw,
                "source": c.source_field,
                "rule": c.rule_code,
            })
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
            "customer_priority": _json_object(j.judgment).get("customer_priority") if j else None,
            "judged_at": _iso(j.created_at) if j else None,
            "created_at": _iso(collected_at),
        })
    return items


def _social_items_complete(db: Session, users: list[XhsUser]) -> list[dict[str, Any]]:
    if not users:
        return []
    user_ids = [u.id for u in users]
    contacts_by_user = _contacts_by_user(db, user_ids)
    comments_by_user = _recent_comments_by_user(db, user_ids)
    notes_by_user = _recent_notes_by_user(db, user_ids)
    sources_by_user = _sources_by_user(db, user_ids)
    history_by_user = _history_by_user(db, user_ids)
    judgments = _latest_judgments(db, user_ids)

    items: list[dict[str, Any]] = []
    for u in users:
        collected_at = u.last_seen_at or u.first_seen_at or u.created_at
        contacts = contacts_by_user.get(u.id, [])
        comments = comments_by_user.get(u.id, [])
        notes = notes_by_user.get(u.id, [])
        sources = sources_by_user.get(u.id) or _json_object_list(getattr(u, "sources_json", None), 6)
        history = history_by_user.get(u.id) or _json_object_list(getattr(u, "history_posts_json", None), 6)
        raw_user = _json_object(getattr(u, "raw_json", None))
        contact_signals = _json_value(u.contact_signals, {})
        platform_signals = _json_value(u.platform_signals, {})
        profile_quality = _json_value(getattr(u, "profile_quality", None), {})
        j = judgments.get(u.id)
        judgment_data = _json_value(j.judgment if j else None, None)
        note_count = _first_number(u.note_count, len(notes))
        follower_count = _first_number(u.follower_count, getattr(u, "followers_count", None))

        items.append({
            "id": u.id,
            "kind": "social",
            "kind_label": "社媒博主",
            "name": _first_text(u.username_clean, getattr(u, "username", None), u.account_clean, getattr(u, "account", None), u.xhs_user_id, "未命名博主"),
            "subtitle": _first_text(u.location_text, u.account_clean, getattr(u, "account", None), ""),
            "platform": u.platform,
            "external_user_id": u.external_user_id,
            "xhs_user_id": u.xhs_user_id,
            "account": _first_text(u.account_clean, getattr(u, "account", None), u.xhs_user_id, ""),
            "avatar_url": u.avatar_url,
            "followers": follower_count,
            "following": u.following_count,
            "liked_collect_count": u.liked_collect_count,
            "profile_note_count": note_count,
            "notes_count": max(note_count or 0, len(notes)),
            "source_notes_count": len(notes),
            "comments_count": len(comments),
            "has_contact": int(u.has_contact or 0),
            "contact": _contact_display([{"type": c["type"], "value": c["value"]} for c in contacts]),
            "contacts": contacts,
            "profile_url": _first_text(u.canonical_profile_url, getattr(u, "profile_url", None), ""),
            "bio": _first_text(u.bio_clean, getattr(u, "bio", None), raw_user.get("bio"), ""),
            "location": u.location_text,
            "clean_status": u.clean_status,
            "contact_signals": _signal_terms(contact_signals),
            "platform_signals": _signal_terms(platform_signals),
            "contact_signals_data": contact_signals,
            "platform_signals_data": platform_signals,
            "profile_quality": profile_quality,
            "recent_comments": comments,
            "recent_notes": notes,
            "source_samples": sources,
            "history_posts": history,
            "raw_user": _small_raw(raw_user),
            "fit_score": j.fit_score if j else None,
            "fit_level": j.fit_level if j else None,
            "decision": j.decision if j else None,
            "intent_type": j.intent_type if j else None,
            "judgment": j.judgment if j else None,
            "judgment_data": judgment_data,
            "customer_priority": judgment_data.get("customer_priority") if isinstance(judgment_data, dict) else None,
            "judgment_evidence": _first_text(
                judgment_data.get("evidence") if isinstance(judgment_data, dict) else None,
                judgment_data.get("reason") if isinstance(judgment_data, dict) else None,
                "",
            ),
            "judgment_suggestion": judgment_data.get("suggestion") if isinstance(judgment_data, dict) else None,
            "judged_at": _iso(j.created_at) if j else None,
            "profile_collected_at": _iso(getattr(u, "profile_collected_at", None)),
            "created_at": _iso(collected_at),
        })
    return items


def _contacts_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    rows = db.scalars(
        select(XhsExtractedContact)
        .where(XhsExtractedContact.user_id.in_(user_ids))
        .order_by(XhsExtractedContact.created_at.desc())
    ).all()
    for c in rows:
        contact_type = _social_contact_type(c)
        out.setdefault(c.user_id or "", []).append({
            "type": contact_type,
            "label": _social_contact_label(contact_type),
            "value": c.value_raw,
            "source": c.source_field,
            "rule": c.rule_code,
        })
    return {uid: vals[:8] for uid, vals in out.items()}


def _recent_comments_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    rows = db.execute(
        select(XhsComment, XhsNote)
        .outerjoin(XhsNote, XhsComment.note_id == XhsNote.id)
        .where(XhsComment.user_id.in_(user_ids))
        .order_by(func.coalesce(XhsComment.last_seen_at, XhsComment.published_at, XhsComment.created_at).desc())
    ).all()
    for comment, note in rows:
        bucket = out.setdefault(comment.user_id or "", [])
        if len(bucket) >= 6:
            continue
        raw = _json_object(comment.raw_json)
        bucket.append({
            "id": comment.id,
            "content": _first_text(comment.content_clean, getattr(comment, "content", None), raw.get("content"), ""),
            "location": _first_text(comment.location_text, getattr(comment, "location", None), raw.get("location"), ""),
            "like_count": comment.like_count,
            "like_count_text": getattr(comment, "like_count_text", None) or raw.get("like_count_text"),
            "published_at_text": getattr(comment, "published_at_text", None) or raw.get("published_at_text"),
            "created_at": _iso(comment.published_at or comment.created_at),
            "depth": comment.depth,
            "note_title": _first_text(note.title_clean if note else None, raw.get("note_title"), ""),
            "note_url": _first_text(getattr(comment, "note_url", None), note.canonical_note_url if note else None, raw.get("note_url"), raw.get("post_url"), ""),
            "keyword": getattr(comment, "keyword", None) or raw.get("keyword"),
        })
    return out


def _recent_notes_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    rows = db.scalars(
        select(XhsNote)
        .where(XhsNote.author_user_id.in_(user_ids))
        .order_by(func.coalesce(XhsNote.last_seen_at, XhsNote.published_at, XhsNote.created_at).desc())
    ).all()
    for note in rows:
        bucket = out.setdefault(note.author_user_id or "", [])
        if len(bucket) >= 6:
            continue
        raw = _json_object(note.raw_json)
        images = _json_list(getattr(note, "images_json", None)) or _json_list(raw.get("image_urls"))
        bucket.append({
            "id": note.id,
            "title": _first_text(note.title_clean, getattr(note, "title", None), raw.get("title"), ""),
            "desc": _first_text(note.desc_clean, getattr(note, "content", None), raw.get("desc"), ""),
            "url": _first_text(note.canonical_note_url, getattr(note, "url", None), raw.get("url"), raw.get("post_url"), ""),
            "cover_url": _first_text(getattr(note, "cover_url", None), raw.get("cover_url"), images[0] if images else None, ""),
            "images": images[:4],
            "like_count": note.like_count,
            "collect_count": note.collect_count,
            "comment_count": note.comment_count,
            "published_at_text": getattr(note, "published_at_text", None) or raw.get("published_at_text"),
            "created_at": _iso(note.published_at or note.created_at),
            "keyword": getattr(note, "keyword", None) or raw.get("keyword"),
        })
    return out


def _sources_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    rows = db.scalars(
        select(XhsUserSource)
        .where(XhsUserSource.user_id.in_(user_ids))
        .order_by(XhsUserSource.created_at.desc())
    ).all()
    for source in rows:
        bucket = out.setdefault(source.user_id, [])
        if len(bucket) >= 6:
            continue
        bucket.append({
            "source_type": source.source_type,
            "keyword": source.keyword,
            "evidence_text": source.evidence_text,
            "evidence_url": source.evidence_url,
            "evidence_images": _json_list(source.evidence_images),
            "comment_depth": source.comment_depth,
            "created_at": _iso(source.created_at),
        })
    return out


def _history_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    rows = db.scalars(
        select(XhsUserHistoryPost)
        .where(XhsUserHistoryPost.user_id.in_(user_ids))
        .order_by(XhsUserHistoryPost.user_id, XhsUserHistoryPost.position.asc())
    ).all()
    for post in rows:
        bucket = out.setdefault(post.user_id, [])
        if len(bucket) >= 6:
            continue
        bucket.append({
            "title": post.title_clean or post.title_raw,
            "url": post.canonical_note_url,
            "cover_url": post.cover_url,
            "like_count": post.like_count,
            "like_count_text": post.like_count_text,
            "published_at_text": post.published_at_text,
            "position": post.position,
        })
    return out


def _latest_judgments(db: Session, user_ids: list[str]) -> dict[str, XhsAiJudgment]:
    judgments: dict[str, XhsAiJudgment] = {}
    for judgment in db.scalars(
        select(XhsAiJudgment)
        .where(XhsAiJudgment.user_id.in_(user_ids), XhsAiJudgment.prompt_version == PROMPT_VERSION)
        .order_by(XhsAiJudgment.user_id, XhsAiJudgment.created_at.desc())
    ).all():
        if judgment.user_id not in judgments:
            judgments[judgment.user_id] = judgment
    return judgments


def _json_value(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _json_object(value: Any) -> dict[str, Any]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[Any]:
    parsed = _json_value(value, [])
    return parsed if isinstance(parsed, list) else []


def _json_object_list(value: Any, limit: int = 6) -> list[dict[str, Any]]:
    return [item for item in _json_list(value) if isinstance(item, dict)][:limit]


def _signal_terms(value: Any) -> list[str]:
    if isinstance(value, dict):
        terms = value.get("terms")
        if isinstance(terms, list):
            return [str(term) for term in terms if str(term or "").strip()][:8]
        return [str(k) for k, v in value.items() if v][:8]
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()][:8]
    return []


def _small_raw(value: dict[str, Any]) -> dict[str, Any]:
    keys = ("user_id", "username", "account", "profile_url", "bio", "location", "stats_text")
    return {key: value.get(key) for key in keys if value.get(key) not in (None, "", [])}


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _first_number(*values: Any) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


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
