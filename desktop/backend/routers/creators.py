"""
Creator list endpoints — backed by the remote X9 API.

Phase 1 of the migration: all SELECTs against the local SQLite `creators`
table are replaced with calls to `services.remote_creators`, with
filtering/sorting performed in Python on the cached row list.

Note on the `/by-tag/{tag_code}` endpoint: it still queries the local
`creator_tags` table because that table hasn't been migrated to the remote
yet. Phase 3 will move it. Until then, by-tag returns whatever local data
is still around (may be stale if writes have already moved to remote).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Iterable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..database.connection import SessionLocal
from ..models.creator import Creator
from ..models.outreach_email import OutreachEmail
from ..services import remote_creators
from ..services.departments import current_department_code, department_where, filter_rows_for_department, row_in_department
from ..services.outreach_lock_service import active_lock_summaries, filter_rows_visible_by_lock, is_admin_user
from ..services.post_processing import create_outreach_event
from ..services.remote_creators import RemoteRepoError
from ..services.tag_engine import find_creators_by_tags
from ..utils.contact_methods import CONTACT_CHANNEL_TERMS, contact_types_for, extract_contact_methods
from ..utils.json_utils import loads_json_list
from ..utils.source_classify import ALL_SOURCES, classify_source


router = APIRouter(prefix="/api/local/creators", tags=["creators"])


class AssignmentIn(BaseModel):
    owner_bd: str | None = None
    store_assigned: str | None = None
    current_status: str | None = None
    force: bool = False


_LOCAL_LIST_COLUMNS = (
    Creator.id,
    Creator.department_code,
    Creator.platform,
    Creator.handle,
    Creator.display_name,
    Creator.profile_url,
    Creator.bio,
    Creator.followers_raw,
    Creator.followers_count,
    Creator.source,
    Creator.avatar_url,
    Creator.shop_profile_url,
    Creator.lead_status,
    Creator.email,
    Creator.has_email,
    Creator.external_links_json,
    Creator.search_keyword,
    Creator.collected_at,
    Creator.last_seen_at,
    Creator.created_at,
    Creator.updated_at,
    Creator.primary_product_category,
    Creator.primary_product_fit_score,
    Creator.feminine_care_fit,
    Creator.commercial_value_score,
    Creator.data_quality_score,
    Creator.contactability_score,
    Creator.content_format_score,
    Creator.content_format_status,
    Creator.fit_level,
    Creator.priority_score,
    Creator.recommendation_score,
    Creator.recommendation_status,
    Creator.current_status,
    Creator.store_assigned,
    Creator.owner_bd,
    Creator.recommended_product_type,
    Creator.recommended_collab_type,
    Creator.outreach_priority,
    Creator.queue_type,
    Creator.review_required,
    Creator.review_status,
    Creator.recommendation_reason,
    Creator.next_action,
    Creator.risk_summary,
    Creator.risk_tags_json,
    Creator.positive_tags_json,
    Creator.evidence_strength,
    Creator.fit_evidence_source_json,
    Creator.matched_keywords_json,
)


# ---------------------------------------------------------------------------
# Date / time helpers (unchanged)
# ---------------------------------------------------------------------------


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        return _parse_day(value)


def _collected_bounds(
    collected_range: str | None = None,
    collected_date: str | None = None,
    collected_from: str | None = None,
    collected_to: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    if collected_date:
        start = _parse_day(collected_date)
        if start is None:
            raise HTTPException(status_code=400, detail="collected_date must be YYYY-MM-DD")
        return start, start + timedelta(days=1)

    now = datetime.now()
    if collected_range:
        aliases = {
            "day": "1d", "last_day": "1d", "recent_day": "1d",
            "week": "7d", "last_week": "7d", "recent_week": "7d",
            "month": "30d", "last_month": "30d", "recent_month": "30d",
        }
        value = aliases.get(collected_range, collected_range)
        if value == "1d":
            return now - timedelta(days=1), None
        if value == "7d":
            return now - timedelta(days=7), None
        if value == "30d":
            return now - timedelta(days=30), None
        raise HTTPException(status_code=400, detail="collected_range must be 1d, 7d or 30d")

    return _parse_datetime(collected_from), _parse_datetime(collected_to)


def _row_collected_dt(row: dict) -> datetime | None:
    return _parse_datetime(row.get("collected_at"))


# ---------------------------------------------------------------------------
# Ranking helpers — Python ports of the SQLAlchemy `case` expressions
# ---------------------------------------------------------------------------


def _priority_rank_value(row: dict) -> int:
    return {"P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(row.get("outreach_priority"), 9)


def _bio_contact_terms(*channels: str) -> list[str]:
    if not channels:
        channels = tuple(CONTACT_CHANNEL_TERMS)
    terms: list[str] = []
    for channel in channels:
        terms.extend(CONTACT_CHANNEL_TERMS.get(channel, ()))
    return list(dict.fromkeys(terms))


def _bio_has_contact(bio_lower: str, *channels: str) -> bool:
    return any(term.lower() in bio_lower for term in _bio_contact_terms(*channels))


_CONTACT_RANK_PATTERNS = [
    (1, lambda has_email, bio: has_email),
    (2, lambda has_email, bio: "whatsapp" in bio or "wa.me" in bio or "wa:" in bio),
    (3, lambda has_email, bio: "telegram" in bio or "t.me/" in bio),
    (4, lambda has_email, bio: "line.me" in bio),
    (5, lambda has_email, bio: "instagram" in bio or "insta" in bio
        or "ig @" in bio or "ig:" in bio),
    (6, lambda has_email, bio: "linktr.ee" in bio or "beacons.ai" in bio),
]


def _contact_rank_value(row: dict) -> int:
    bio = (row.get("bio") or "").lower()
    has_email = bool(row.get("has_email"))
    for rank, pred in _CONTACT_RANK_PATTERNS:
        if pred(has_email, bio):
            return rank
    return 9


def _contact_channel_match(row: dict, channel: str) -> bool:
    value = channel.strip().lower()
    bio = (row.get("bio") or "").lower()
    has_email = bool(row.get("has_email"))
    if value in {"any", "contactable"}:
        return has_email or "@" in bio or _bio_has_contact(bio)
    if value in {"none", "no_contact", "missing"}:
        return (not has_email) and ("@" not in bio) and (not _bio_has_contact(bio))
    if value == "email":
        return has_email or "@" in bio
    if value in CONTACT_CHANNEL_TERMS:
        return _bio_has_contact(bio, value)
    raise HTTPException(
        status_code=400,
        detail="contact_channel must be any, email, whatsapp, instagram, link, telegram, line, facebook, dm, phone or no_contact",
    )


SOURCE_LABELS = {
    "tiktok_shop": "TikTok Shop",
    "x9_leads": "X9 线索",
    "table_import": "表格导入",
    "other": "其他",
}


def _creator_source(row: dict) -> str:
    return classify_source(row.get("platform"), row.get("source"))


def _source_tags(row: dict) -> list[str]:
    tags = [_creator_source(row)]
    raw_source = str(row.get("source") or "").strip()
    if raw_source and raw_source not in tags:
        tags.append(raw_source)
    return tags


# ---------------------------------------------------------------------------
# Sort
# ---------------------------------------------------------------------------


def _date_seconds(s: Any) -> float:
    if not s:
        return 0.0
    if isinstance(s, datetime):
        return s.timestamp()
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _i(row: dict, key: str) -> int:
    v = row.get(key)
    return int(v) if isinstance(v, (int, float)) else 0


def _apply_sort(rows: list[dict], sort_by: str | None) -> list[dict]:
    """Multi-key sort using stable-sort layering (least significant first)."""
    sort_by = sort_by or "recommended"
    if sort_by == "recommended":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "followers_count"))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=_priority_rank_value)
    elif sort_by == "collected_at":
        rows = sorted(rows, key=lambda r: -_i(r, "followers_count"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
    elif sort_by == "followers":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "followers_count"))
    elif sort_by == "score":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "followers_count"))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
    elif sort_by == "fit":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "followers_count"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
    elif sort_by == "priority":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=_priority_rank_value)
    elif sort_by == "contactable":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=_priority_rank_value)
        rows = sorted(rows, key=_contact_rank_value)
    elif sort_by == "micro":
        rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
        rows = sorted(rows, key=lambda r: -_i(r, "primary_product_fit_score"))
        rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
        rows = sorted(rows, key=lambda r: _i(r, "followers_count"))  # ASC
    else:
        raise HTTPException(
            status_code=400,
            detail="sort_by must be recommended, collected_at, followers, score, fit, priority, contactable or micro",
        )
    return rows


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def _apply_filters(
    rows: Iterable[dict],
    *,
    source: str | None,
    queue_type: str | None,
    has_email: bool | None,
    search_keyword: str | None,
    handle_contains: str | None,
    contact_contains: str | None,
    contact_channel: str | None,
    bio_contains: str | None,
    outreach_priority: str | None,
    recommended_product_type: str | None,
    recommended_collab_type: str | None,
    recommendation_status: str | None,
    current_status: str | None,
    owner_bd_contains: str | None,
    store_assigned_contains: str | None,
    unassigned: bool | None,
    reason_contains: str | None,
    min_followers: int | None,
    max_followers: int | None,
    min_score: int | None,
    max_score: int | None,
    min_fit_score: int | None,
    max_fit_score: int | None,
    collected_start: datetime | None,
    collected_end: datetime | None,
) -> list[dict]:
    out: list[dict] = []
    handle_q = handle_contains.lower() if handle_contains else None
    bio_q = bio_contains.lower() if bio_contains else None
    contact_q = contact_contains.lower() if contact_contains else None
    reason_q = reason_contains.lower() if reason_contains else None
    owner_q = owner_bd_contains.lower() if owner_bd_contains else None
    store_q = store_assigned_contains.lower() if store_assigned_contains else None

    for r in rows:
        if source and source not in {"all", _creator_source(r)}:
            continue
        if queue_type is not None and r.get("queue_type") != queue_type:
            continue
        if has_email is True and not r.get("has_email"):
            continue
        if has_email is False and r.get("has_email"):
            continue
        if search_keyword is not None and r.get("search_keyword") != search_keyword:
            continue
        if handle_q and handle_q not in (r.get("handle") or "").lower():
            continue
        if contact_q:
            email = (r.get("email") or "").lower()
            bio = (r.get("bio") or "").lower()
            if contact_q not in email and contact_q not in bio:
                continue
        if contact_channel and not _contact_channel_match(r, contact_channel):
            continue
        if bio_q and bio_q not in (r.get("bio") or "").lower():
            continue
        if outreach_priority is not None and r.get("outreach_priority") != outreach_priority:
            continue
        if recommended_product_type is not None and r.get("recommended_product_type") != recommended_product_type:
            continue
        if recommended_collab_type is not None and r.get("recommended_collab_type") != recommended_collab_type:
            continue
        if recommendation_status is not None and r.get("recommendation_status") != recommendation_status:
            continue
        if current_status is not None and r.get("current_status") != current_status:
            continue
        if unassigned is True and (r.get("owner_bd") or "").strip():
            continue
        if unassigned is False and not (r.get("owner_bd") or "").strip():
            continue
        if owner_q and owner_q not in (r.get("owner_bd") or "").lower():
            continue
        if store_q and store_q not in (r.get("store_assigned") or "").lower():
            continue
        if reason_q and reason_q not in (r.get("recommendation_reason") or "").lower():
            continue
        followers = r.get("followers_count")
        # Match SQL semantics: NULL fails BOTH `>= min` and `<= max` comparisons,
        # so NULL rows get filtered out whenever a follower bound is set.
        if min_followers is not None and (followers is None or followers < min_followers):
            continue
        if max_followers is not None and (followers is None or followers > max_followers):
            continue
        score = r.get("recommendation_score")
        if min_score is not None and (score or 0) < min_score:
            continue
        if max_score is not None and (score or 0) > max_score:
            continue
        fit = r.get("primary_product_fit_score")
        if min_fit_score is not None and (fit or 0) < min_fit_score:
            continue
        if max_fit_score is not None and (fit or 0) > max_fit_score:
            continue
        if collected_start is not None or collected_end is not None:
            row_dt = _row_collected_dt(r)
            if collected_start is not None and (row_dt is None or row_dt < collected_start):
                continue
            if collected_end is not None and (row_dt is None or row_dt >= collected_end):
                continue
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Outreach signal aggregation (local SQLite — outreach_emails)
# ---------------------------------------------------------------------------


def _creator_id_key(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _fetch_outreach_signals(creator_ids: Iterable[str]) -> dict[str, dict]:
    """For a list of creator ids, batch-fetch:
        outreach_count             — # of ``status='sent'`` emails
        last_outreach_sender_email — most recent ``from_email`` of a sent email
        last_outreach_at           — its ``sent_at`` ISO string

    Empty dict for creators with no outreach yet.
    """
    ids = list(dict.fromkeys(cid for cid in (_creator_id_key(value) for value in creator_ids) if cid))
    if not ids:
        return {}

    out: dict[str, dict] = {}
    with SessionLocal() as db:
        # Counts of sent emails
        count_rows = db.execute(
            select(OutreachEmail.creator_id, func.count(OutreachEmail.id))
            .where(OutreachEmail.creator_id.in_(ids))
            .where(OutreachEmail.status == "sent")
            .group_by(OutreachEmail.creator_id)
        ).all()
        for cid, n in count_rows:
            out.setdefault(cid, {})["outreach_count"] = int(n)

        # Most recent sent email per creator (single SQL pass: order then dedup
        # on the Python side — clearer than a window function for SQLite)
        latest_rows = db.execute(
            select(
                OutreachEmail.creator_id,
                OutreachEmail.from_email,
                OutreachEmail.sent_at,
            )
            .where(OutreachEmail.creator_id.in_(ids))
            .where(OutreachEmail.status == "sent")
            .order_by(OutreachEmail.creator_id, OutreachEmail.sent_at.desc())
        ).all()
        for cid, from_email, sent_at in latest_rows:
            slot = out.setdefault(cid, {})
            if "last_outreach_sender_email" in slot:
                continue  # already kept the most-recent row for this creator
            slot["last_outreach_sender_email"] = from_email
            slot["last_outreach_at"] = sent_at.isoformat() if hasattr(sent_at, "isoformat") else (str(sent_at) if sent_at else None)

    # Ensure default keys for any partial slot
    for slot in out.values():
        slot.setdefault("outreach_count", 0)
        slot.setdefault("last_outreach_sender_email", None)
        slot.setdefault("last_outreach_at", None)
    return out


# ---------------------------------------------------------------------------
# Serialization (now from dicts instead of Creator instances)
# ---------------------------------------------------------------------------


def _serialize(c: dict, signal: dict | None = None) -> dict[str, Any]:
    email = c.get("email")
    bio = c.get("bio")
    external_links = c.get("external_links_json")
    contact_methods = extract_contact_methods(email, bio, external_links)
    source_key = _creator_source(c)
    category_tags = loads_json_list(c.get("category_tags_json"))
    if not category_tags and c.get("primary_product_category"):
        category_tags = [c.get("primary_product_category")]
    return {
        "id": c.get("id"),
        "department_code": c.get("department_code") or "cross_border",
        "handle": c.get("handle"),
        "display_name": c.get("display_name"),
        "profile_url": c.get("profile_url"),
        "bio": bio,
        "followers_count": c.get("followers_count"),
        "followers": c.get("followers_count"),
        "followers_raw": c.get("followers_raw"),
        "source": source_key,
        "source_label": SOURCE_LABELS.get(source_key, "其他"),
        "source_tags": _source_tags(c),
        "avatar_url": c.get("avatar_url"),
        "shop_profile_url": c.get("shop_profile_url"),
        "lead_status": c.get("lead_status"),
        "email": email,
        "has_email": bool(c.get("has_email")),
        "has_contact": bool(contact_methods),
        "contact_methods": contact_methods,
        "contact_types": contact_types_for(email, bio, external_links),
        "external_links": loads_json_list(external_links),
        "search_keyword": c.get("search_keyword"),
        "collected_at": c.get("collected_at"),
        "last_seen_at": c.get("last_seen_at"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "primary_product_category": c.get("primary_product_category"),
        "category_tags": category_tags,
        "country": c.get("country"),
        "language": c.get("language"),
        "tier": c.get("tier") or c.get("outreach_priority"),
        "primary_product_fit_score": c.get("primary_product_fit_score"),
        "feminine_care_fit": c.get("feminine_care_fit"),
        "commercial_value_score": c.get("commercial_value_score"),
        "data_quality_score": c.get("data_quality_score"),
        "contactability_score": c.get("contactability_score"),
        "content_format_score": c.get("content_format_score"),
        "content_format_status": c.get("content_format_status"),
        "fit_level": c.get("fit_level"),
        "priority_score": c.get("priority_score"),
        "recommendation_score": c.get("recommendation_score"),
        "recommendation_status": c.get("recommendation_status"),
        "current_status": c.get("current_status"),
        "store_assigned": c.get("store_assigned"),
        "owner_bd": c.get("owner_bd"),
        "recommended_product_type": c.get("recommended_product_type"),
        "recommended_collab_type": c.get("recommended_collab_type"),
        "outreach_priority": c.get("outreach_priority"),
        "queue_type": c.get("queue_type"),
        "review_required": bool(c.get("review_required")),
        "review_status": c.get("review_status"),
        "recommendation_reason": c.get("recommendation_reason"),
        "next_action": c.get("next_action"),
        "risk_summary": c.get("risk_summary"),
        "risk_tags": loads_json_list(c.get("risk_tags_json")),
        "positive_tags": loads_json_list(c.get("positive_tags_json")),
        "evidence_strength": c.get("evidence_strength"),
        "fit_evidence_sources": loads_json_list(c.get("fit_evidence_source_json")),
        "matched_keywords": loads_json_list(c.get("matched_keywords_json")),
        "profile_snapshot": _load_json_dict(c.get("profile_snapshot_json")),
        "tiktok_shop": _load_json_dict(c.get("tiktok_shop_json")),
        # Outreach signals (joined from local outreach_emails)
        "outreach_count": (signal or {}).get("outreach_count", 0),
        "last_outreach_sender_email": (signal or {}).get("last_outreach_sender_email"),
        "last_outreach_at": (signal or {}).get("last_outreach_at"),
    }


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _serialize_local_creator(c) -> dict[str, Any]:
    """Adapter for the by-tag endpoint that still returns SQLAlchemy Creator
    instances. Drops them through `_serialize` by converting attrs to a dict
    on the fly."""
    return _serialize({
        "id": c.id,
        "department_code": c.department_code,
        "handle": c.handle,
        "display_name": c.display_name,
        "profile_url": c.profile_url,
        "bio": c.bio,
        "followers_count": c.followers_count,
        "followers_raw": c.followers_raw,
        "source": c.source,
        "avatar_url": c.avatar_url,
        "shop_profile_url": c.shop_profile_url,
        "lead_status": c.lead_status,
        "email": c.email,
        "has_email": c.has_email,
        "external_links_json": c.external_links_json,
        "search_keyword": c.search_keyword,
        "collected_at": c.collected_at.isoformat() if c.collected_at else None,
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "primary_product_category": c.primary_product_category,
        "primary_product_fit_score": c.primary_product_fit_score,
        "feminine_care_fit": c.feminine_care_fit,
        "commercial_value_score": c.commercial_value_score,
        "data_quality_score": c.data_quality_score,
        "contactability_score": c.contactability_score,
        "content_format_score": c.content_format_score,
        "content_format_status": c.content_format_status,
        "fit_level": c.fit_level,
        "priority_score": c.priority_score,
        "recommendation_score": c.recommendation_score,
        "recommendation_status": c.recommendation_status,
        "current_status": c.current_status,
        "store_assigned": c.store_assigned,
        "owner_bd": c.owner_bd,
        "recommended_product_type": c.recommended_product_type,
        "recommended_collab_type": c.recommended_collab_type,
        "outreach_priority": c.outreach_priority,
        "queue_type": c.queue_type,
        "review_required": c.review_required,
        "review_status": c.review_status,
        "recommendation_reason": c.recommendation_reason,
        "next_action": c.next_action,
        "risk_summary": c.risk_summary,
        "risk_tags_json": c.risk_tags_json,
        "positive_tags_json": c.positive_tags_json,
        "evidence_strength": c.evidence_strength,
        "fit_evidence_source_json": c.fit_evidence_source_json,
        "matched_keywords_json": c.matched_keywords_json,
        "profile_snapshot_json": c.profile_snapshot_json,
        "tiktok_shop_json": c.tiktok_shop_json,
    })


def _local_creator_row(c: Creator) -> dict[str, Any]:
    return {
        "id": c.id,
        "department_code": c.department_code,
        "platform": c.platform,
        "handle": c.handle,
        "display_name": c.display_name,
        "profile_url": c.profile_url,
        "bio": c.bio,
        "followers_raw": c.followers_raw,
        "followers_count": c.followers_count,
        "source": c.source,
        "avatar_url": c.avatar_url,
        "shop_profile_url": c.shop_profile_url,
        "lead_status": c.lead_status,
        "email": c.email,
        "has_email": c.has_email,
        "external_links_json": c.external_links_json,
        "search_keyword": c.search_keyword,
        "collected_at": c.collected_at.isoformat() if c.collected_at else None,
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "primary_product_category": c.primary_product_category,
        "primary_product_fit_score": c.primary_product_fit_score,
        "feminine_care_fit": c.feminine_care_fit,
        "commercial_value_score": c.commercial_value_score,
        "data_quality_score": c.data_quality_score,
        "contactability_score": c.contactability_score,
        "content_format_score": c.content_format_score,
        "content_format_status": c.content_format_status,
        "fit_level": c.fit_level,
        "priority_score": c.priority_score,
        "recommendation_score": c.recommendation_score,
        "recommendation_status": c.recommendation_status,
        "current_status": c.current_status,
        "store_assigned": c.store_assigned,
        "owner_bd": c.owner_bd,
        "recommended_product_type": c.recommended_product_type,
        "recommended_collab_type": c.recommended_collab_type,
        "outreach_priority": c.outreach_priority,
        "queue_type": c.queue_type,
        "review_required": c.review_required,
        "review_status": c.review_status,
        "recommendation_reason": c.recommendation_reason,
        "next_action": c.next_action,
        "risk_summary": c.risk_summary,
        "risk_tags_json": c.risk_tags_json,
        "positive_tags_json": c.positive_tags_json,
        "evidence_strength": c.evidence_strength,
        "fit_evidence_source_json": c.fit_evidence_source_json,
        "matched_keywords_json": c.matched_keywords_json,
        "profile_snapshot_json": c.profile_snapshot_json,
        "tiktok_shop_json": c.tiktok_shop_json,
    }


def _local_creator_list_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("collected_at", "last_seen_at", "created_at", "updated_at"):
        value = out.get(key)
        if hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    # List pages must not materialize large snapshots; details load one creator.
    out["profile_snapshot_json"] = None
    out["tiktok_shop_json"] = None
    return out


def _all_creator_rows(department_code: str | None) -> list[dict]:
    rows: list[dict] = []
    if not settings.db_url.startswith("sqlite"):
        try:
            rows = filter_rows_for_department(_wrap_remote(remote_creators.list_all), department_code)
        except HTTPException:
            rows = []
    seen = {
        (str(row.get("platform") or "tiktok").lower(), str(row.get("handle") or "").lower())
        for row in rows
        if row.get("handle")
    }
    with SessionLocal() as db:
        stmt = select(*_LOCAL_LIST_COLUMNS)
        where_clause = department_where(Creator, department_code)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        local_rows = list(db.execute(stmt).mappings())
    for row in local_rows:
        creator = _local_creator_list_row(row)
        key = ((creator.get("platform") or "tiktok").lower(), (creator.get("handle") or "").lower())
        if key in seen:
            continue
        rows.append(creator)
        seen.add(key)
    return rows


# ---------------------------------------------------------------------------
# Common error handling
# ---------------------------------------------------------------------------


def _wrap_remote(call):
    try:
        return call()
    except RemoteRepoError as e:
        raise HTTPException(status_code=502, detail=f"remote API unavailable: {e}")


def _apply_outreach_lock_visibility(rows: list[dict], user: dict[str, Any] | None) -> tuple[list[dict], dict[str, dict[str, Any]]]:
    with SessionLocal() as db:
        return filter_rows_visible_by_lock(db, rows, user)


def _serialize_with_signals(
    rows: list[dict],
    user: dict[str, Any] | None = None,
    lock_summaries: dict[str, dict[str, Any]] | None = None,
) -> list[dict]:
    """Serialize a list of remote creator dicts and merge in their outreach
    signals from local SQLite in a single batch."""
    signals = _fetch_outreach_signals([r.get("id") for r in rows])
    if lock_summaries is None:
        with SessionLocal() as db:
            lock_summaries = active_lock_summaries(db, [r.get("id") for r in rows], user)
    items: list[dict[str, Any]] = []
    for row in rows:
        key = _creator_id_key(row.get("id"))
        item = _serialize(row, signals.get(key))
        if key and (lock := lock_summaries.get(key)):
            item["outreach_lock"] = lock
        items.append(item)
    return items


def _attach_lock_or_hide(item: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    creator_id = _creator_id_key(item.get("id"))
    if not creator_id:
        return item
    with SessionLocal() as db:
        locks = active_lock_summaries(db, [creator_id], user)
    lock = locks.get(creator_id)
    if lock and not lock.get("is_mine") and not is_admin_user(user):
        raise HTTPException(status_code=404, detail="creator not found")
    if lock:
        item["outreach_lock"] = lock
    return item


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
def list_all(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    source: str | None = Query(default=None),
    queue_type: str | None = None,
    has_email: bool | None = None,
    search_keyword: str | None = None,
    handle_contains: str | None = None,
    contact_contains: str | None = None,
    contact_channel: str | None = None,
    bio_contains: str | None = None,
    outreach_priority: str | None = None,
    recommended_product_type: str | None = None,
    recommended_collab_type: str | None = None,
    recommendation_status: str | None = None,
    current_status: str | None = None,
    owner_bd_contains: str | None = None,
    store_assigned_contains: str | None = None,
    unassigned: bool | None = None,
    reason_contains: str | None = None,
    min_followers: int | None = None,
    max_followers: int | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    min_fit_score: int | None = None,
    max_fit_score: int | None = None,
    collected_range: str | None = Query(default=None),
    collected_date: str | None = Query(default=None),
    collected_from: str | None = Query(default=None),
    collected_to: str | None = Query(default=None),
    sort_by: str | None = Query(default="recommended"),
) -> dict:
    if source and source not in {"all", *ALL_SOURCES}:
        raise HTTPException(status_code=400, detail="source must be all, tiktok_shop, x9_leads, table_import or other")
    current_user = getattr(request.state, "current_user", None) or {}
    collected_start, collected_end = _collected_bounds(
        collected_range, collected_date, collected_from, collected_to
    )
    department_code = current_department_code(request)
    rows = _all_creator_rows(department_code)
    rows = _apply_filters(
        rows,
        source=source,
        queue_type=queue_type,
        has_email=has_email,
        search_keyword=search_keyword,
        handle_contains=handle_contains,
        contact_contains=contact_contains,
        contact_channel=contact_channel,
        bio_contains=bio_contains,
        outreach_priority=outreach_priority,
        recommended_product_type=recommended_product_type,
        recommended_collab_type=recommended_collab_type,
        recommendation_status=recommendation_status,
        current_status=current_status,
        owner_bd_contains=owner_bd_contains,
        store_assigned_contains=store_assigned_contains,
        unassigned=unassigned,
        reason_contains=reason_contains,
        min_followers=min_followers,
        max_followers=max_followers,
        min_score=min_score,
        max_score=max_score,
        min_fit_score=min_fit_score,
        max_fit_score=max_fit_score,
        collected_start=collected_start,
        collected_end=collected_end,
    )
    rows = _apply_sort(rows, sort_by)
    rows, lock_summaries = _apply_outreach_lock_visibility(rows, current_user)
    page = rows[offset:offset + limit]
    return {"ok": True, "total": len(rows), "items": _serialize_with_signals(page, current_user, lock_summaries)}


@router.get("/recommended")
def list_recommended(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    source: str | None = Query(default=None),
    collected_range: str | None = Query(default=None),
    collected_date: str | None = Query(default=None),
    collected_from: str | None = Query(default=None),
    collected_to: str | None = Query(default=None),
) -> dict:
    if source and source not in {"all", *ALL_SOURCES}:
        raise HTTPException(status_code=400, detail="source must be all, tiktok_shop, x9_leads, table_import or other")
    current_user = getattr(request.state, "current_user", None) or {}
    collected_start, collected_end = _collected_bounds(
        collected_range, collected_date, collected_from, collected_to
    )
    statuses = {"recommended", "recommended_after_review", "low_cost_test", "affiliate_test"}
    department_code = current_department_code(request)
    rows = _all_creator_rows(department_code)
    rows = [r for r in rows if r.get("recommendation_status") in statuses]
    if source is not None or collected_start is not None or collected_end is not None:
        rows = _apply_filters(
            rows,
            source=source,
            queue_type=None, has_email=None, search_keyword=None,
            handle_contains=None, contact_contains=None, contact_channel=None,
            bio_contains=None, outreach_priority=None,
            recommended_product_type=None, recommended_collab_type=None,
            recommendation_status=None, current_status=None,
            owner_bd_contains=None, store_assigned_contains=None, unassigned=None,
            reason_contains=None,
            min_followers=None, max_followers=None,
            min_score=None, max_score=None,
            min_fit_score=None, max_fit_score=None,
            collected_start=collected_start, collected_end=collected_end,
        )
    # Sort: collected_at desc, outreach_priority asc, recommendation_score desc
    rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
    rows = sorted(rows, key=_priority_rank_value)
    rows = sorted(rows, key=lambda r: -_date_seconds(r.get("collected_at")))
    rows, lock_summaries = _apply_outreach_lock_visibility(rows, current_user)
    rows = rows[:limit]
    return {"ok": True, "total": len(rows), "items": _serialize_with_signals(rows, current_user, lock_summaries)}


@router.get("/by-tag/{tag_code}")
def list_by_tag(
    request: Request,
    tag_code: str,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    """NOTE: still queries local SQLite (CreatorTag join). Phase 3 will move
    creator_tags to remote and migrate this endpoint."""
    rows = find_creators_by_tags(db, [tag_code], require_all=False, limit=limit, offset=offset)
    department_code = current_department_code(request)
    rows = [row for row in rows if row_in_department(row, department_code)]
    current_user = getattr(request.state, "current_user", None) or {}
    items = []
    for creator in rows:
        try:
            items.append(_attach_lock_or_hide(_serialize_local_creator(creator), current_user))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return {"ok": True, "total": len(items), "items": items}


@router.get("/by-queue/{queue_code}")
def list_by_queue(request: Request, queue_code: str, limit: int = 200, offset: int = 0) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    rows = _all_creator_rows(current_department_code(request))
    rows = [r for r in rows if r.get("queue_type") == queue_code]
    rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
    rows, lock_summaries = _apply_outreach_lock_visibility(rows, current_user)
    page = rows[offset:offset + limit]
    return {"ok": True, "total": len(rows), "items": _serialize_with_signals(page, current_user, lock_summaries)}


@router.get("/by-product/{product_type}")
def list_by_product(request: Request, product_type: str, limit: int = 200, offset: int = 0) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    rows = _all_creator_rows(current_department_code(request))
    rows = [r for r in rows if r.get("recommended_product_type") == product_type]
    rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
    rows, lock_summaries = _apply_outreach_lock_visibility(rows, current_user)
    page = rows[offset:offset + limit]
    return {"ok": True, "total": len(rows), "items": _serialize_with_signals(page, current_user, lock_summaries)}


@router.get("/by-collab/{collab_type}")
def list_by_collab(request: Request, collab_type: str, limit: int = 200, offset: int = 0) -> dict:
    current_user = getattr(request.state, "current_user", None) or {}
    rows = _all_creator_rows(current_department_code(request))
    rows = [r for r in rows if r.get("recommended_collab_type") == collab_type]
    rows = sorted(rows, key=lambda r: -_i(r, "recommendation_score"))
    rows, lock_summaries = _apply_outreach_lock_visibility(rows, current_user)
    page = rows[offset:offset + limit]
    return {"ok": True, "total": len(rows), "items": _serialize_with_signals(page, current_user, lock_summaries)}


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _local_creator_by_id_or_handle(db: Session, creator_id: str) -> Creator | None:
    local = db.get(Creator, creator_id)
    if local is not None:
        return local
    if "_" in creator_id:
        _prefix, _sep, handle = creator_id.partition("_")
        if handle:
            return db.scalar(select(Creator).where(Creator.handle == handle))
    return db.scalar(select(Creator).where(Creator.handle == creator_id))


def _remote_creator_for_update(creator_id: str, department_code: str | None) -> dict | None:
    if not str(creator_id).isdigit():
        return None
    row = _wrap_remote(lambda: remote_creators.get_by_id(creator_id))
    if row is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(row, department_code):
        raise HTTPException(status_code=404, detail="creator not found")
    return row


def _patch_local_assignment(db: Session, creator: Creator, fields: dict[str, Any]) -> dict:
    for key, value in fields.items():
        if hasattr(creator, key):
            setattr(creator, key, value)
    db.commit()
    db.refresh(creator)
    return _serialize_local_creator(creator)


def _request_user(request: Request) -> dict:
    user = getattr(request.state, "current_user", None)
    if not user:
        raise HTTPException(status_code=401, detail="login required")
    return user


def _actor_id(user: dict) -> str:
    return str(user.get("id") or user.get("identity") or user.get("username") or "")


@router.post("/{creator_id}/claim")
def claim_creator(creator_id: str, body: AssignmentIn, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _request_user(request)
    owner = user.get("email") or user.get("username") or user.get("identity")
    if not owner:
        raise HTTPException(status_code=401, detail="login required")
    is_admin = user.get("role") in {"department_admin", "company_admin", "super_admin"}

    department_code = current_department_code(request)
    row = _remote_creator_for_update(creator_id, department_code)
    if row is not None:
        current_owner = (row.get("owner_bd") or "").strip()
        if current_owner and current_owner.lower() != owner.lower() and not (body.force and is_admin):
            raise HTTPException(status_code=409, detail=f"creator already assigned to {current_owner}")
        fields: dict[str, Any] = {"owner_bd": owner}
        if body.store_assigned is not None:
            fields["store_assigned"] = _clean_text(body.store_assigned)
        if body.current_status is not None:
            fields["current_status"] = _clean_text(body.current_status)
        _wrap_remote(lambda: remote_creators.patch(creator_id, **fields))
        updated = _wrap_remote(lambda: remote_creators.get_by_id(creator_id))
        return {"ok": True, "item": _serialize(updated or {**row, **fields})}

    local = _local_creator_by_id_or_handle(db, creator_id)
    if local is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(local, department_code):
        raise HTTPException(status_code=404, detail="creator not found")
    current_owner = (local.owner_bd or "").strip()
    if current_owner and current_owner.lower() != owner.lower() and not (body.force and is_admin):
        raise HTTPException(status_code=409, detail=f"creator already assigned to {current_owner}")
    fields = {"owner_bd": owner}
    if body.store_assigned is not None:
        fields["store_assigned"] = _clean_text(body.store_assigned)
    if body.current_status is not None:
        fields["current_status"] = _clean_text(body.current_status)
    create_outreach_event(
        db,
        local,
        event_type="assigned",
        actor_user_id=_actor_id(user),
        owner_bd=owner,
        metadata={"source": "creator_claim"},
    )
    return {"ok": True, "item": _patch_local_assignment(db, local, fields)}


@router.post("/{creator_id}/release")
def release_creator(creator_id: str, body: AssignmentIn, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _request_user(request)
    owner = user.get("email") or user.get("username") or user.get("identity")
    is_admin = user.get("role") in {"department_admin", "company_admin", "super_admin"}
    department_code = current_department_code(request)
    row = _remote_creator_for_update(creator_id, department_code)
    if row is not None:
        current_owner = (row.get("owner_bd") or "").strip()
        if owner and current_owner and current_owner.lower() != owner.lower() and not (body.force and is_admin):
            raise HTTPException(status_code=409, detail=f"creator assigned to {current_owner}")
        _wrap_remote(lambda: remote_creators.patch(creator_id, owner_bd=None))
        updated = _wrap_remote(lambda: remote_creators.get_by_id(creator_id))
        return {"ok": True, "item": _serialize(updated or {**row, "owner_bd": None})}

    local = _local_creator_by_id_or_handle(db, creator_id)
    if local is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(local, department_code):
        raise HTTPException(status_code=404, detail="creator not found")
    current_owner = (local.owner_bd or "").strip()
    if owner and current_owner and current_owner.lower() != owner.lower() and not (body.force and is_admin):
        raise HTTPException(status_code=409, detail=f"creator assigned to {current_owner}")
    return {"ok": True, "item": _patch_local_assignment(db, local, {"owner_bd": None})}


@router.patch("/{creator_id}/assignment")
def update_assignment(creator_id: str, body: AssignmentIn, request: Request, db: Session = Depends(get_db)) -> dict:
    user = _request_user(request)
    if user.get("role") not in {"department_admin", "company_admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="admin only")
    fields: dict[str, Any] = {}
    if body.owner_bd is not None:
        fields["owner_bd"] = _clean_text(body.owner_bd)
    if body.store_assigned is not None:
        fields["store_assigned"] = _clean_text(body.store_assigned)
    if body.current_status is not None:
        fields["current_status"] = _clean_text(body.current_status)
    if not fields:
        raise HTTPException(status_code=400, detail="no assignment fields provided")

    department_code = current_department_code(request)
    row = _remote_creator_for_update(creator_id, department_code)
    if row is not None:
        _wrap_remote(lambda: remote_creators.patch(creator_id, **fields))
        updated = _wrap_remote(lambda: remote_creators.get_by_id(creator_id))
        return {"ok": True, "item": _serialize(updated or {**row, **fields})}

    local = _local_creator_by_id_or_handle(db, creator_id)
    if local is None:
        raise HTTPException(status_code=404, detail="creator not found")
    if not row_in_department(local, department_code):
        raise HTTPException(status_code=404, detail="creator not found")
    if fields.get("owner_bd"):
        create_outreach_event(
            db,
            local,
            event_type="assigned",
            actor_user_id=_actor_id(user),
            owner_bd=fields["owner_bd"],
            metadata={"source": "admin_assignment"},
        )
    return {"ok": True, "item": _patch_local_assignment(db, local, fields)}


@router.get("/{creator_id}")
def get_one(creator_id: str, request: Request) -> dict:
    """Look up by id. Accepts either the remote integer id (preferred) or
    a local-style VARCHAR id like `tt_phinyinhi` (treated as a handle
    lookup, with platform inferred from the prefix)."""
    # Try remote integer id first
    department_code = current_department_code(request)
    current_user = getattr(request.state, "current_user", None) or {}
    if creator_id.isdigit():
        row = _wrap_remote(lambda: remote_creators.get_by_id(int(creator_id)))
        if row is None:
            raise HTTPException(status_code=404, detail="creator not found")
        if not row_in_department(row, department_code):
            raise HTTPException(status_code=404, detail="creator not found")
        signals = _fetch_outreach_signals([row.get("id")])
        return _attach_lock_or_hide(_serialize(row, signals.get(row.get("id"))), current_user)

    # Legacy local id like "tt_<handle>" — try mapping to (platform, handle)
    if "_" in creator_id:
        prefix, _, handle = creator_id.partition("_")
        platform_map = {"tt": "tiktok", "ig": "instagram", "yt": "youtube"}
        platform = platform_map.get(prefix)
        if platform and handle:
            row = _wrap_remote(lambda: remote_creators.get_by_handle(platform, handle))
            if row is not None:
                if not row_in_department(row, department_code):
                    raise HTTPException(status_code=404, detail="creator not found")
                signals = _fetch_outreach_signals([row.get("id")])
                return _attach_lock_or_hide(_serialize(row, signals.get(row.get("id"))), current_user)

    with SessionLocal() as db:
        local = db.get(Creator, creator_id)
        if local is not None:
            if not row_in_department(local, department_code):
                raise HTTPException(status_code=404, detail="creator not found")
            return _attach_lock_or_hide(_serialize_local_creator(local), current_user)

    raise HTTPException(status_code=404, detail="creator not found")
