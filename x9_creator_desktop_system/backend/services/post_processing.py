from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import and_, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from ..models.bd_monthly_stat import BdMonthlyStat
from ..models.creator import Creator
from ..models.creator_outreach_event import CreatorOutreachEvent
from ..models.creator_recommendation import CreatorRecommendation
from ..models.creator_source import CreatorSource
from ..models.outreach_email import OutreachEmail
from ..models.review_task import ReviewTask
from ..utils.id_utils import creator_id_for, new_id
from ..utils.json_utils import dumps_json
from ..utils.source_classify import SOURCE_SHOP, SOURCE_TABLE_IMPORT, SOURCE_X9_LEADS, classify_source
from .departments import DEFAULT_DEPARTMENT, normalize_department_code


SOURCE_TIKTOK_SHOP = "tiktok_shop"
SOURCE_TIKTOK_VIDEO = "tiktok_video"
SOURCE_BD = "bd"
SOURCE_OTHER = "other"
SOURCE_TYPES = {SOURCE_TIKTOK_SHOP, SOURCE_TIKTOK_VIDEO, SOURCE_BD, SOURCE_OTHER}
RAW_QUEUE_LEAD_STATUSES = ("shop_list_seen", "shop_queue_cleared")

OUTREACH_EVENT_ORDER = [
    "recommended",
    "assigned",
    "sent",
    "pending_reply",
    "contacted",
    "replied",
    "communicating",
    "confirmed",
    "sample_shipped",
    "sample_delivered",
    "video_published",
    "partnered",
    "ad_authorized",
    "ad_running",
    "dropped",
]
CONTACTED_EVENT_TYPES = {
    "sent",
    "pending_reply",
    "contacted",
    "replied",
    "communicating",
    "confirmed",
    "sample_shipped",
    "sample_delivered",
    "video_published",
    "partnered",
    "ad_authorized",
    "ad_running",
}

RECENT_EVENT_LABELS = {
    "recommended": "推荐",
    "assigned": "分配",
    "sent": "已发送",
    "pending_reply": "待回复",
    "contacted": "已建联",
    "replied": "已回复",
    "communicating": "沟通中",
    "confirmed": "已确认",
    "sample_shipped": "已寄样",
    "sample_delivered": "样品签收",
    "video_published": "视频已发",
    "partnered": "已合作",
    "ad_authorized": "已授权",
    "ad_running": "广告投放中",
    "dropped": "已放弃",
}

EMAIL_EVENT_LABELS = {
    "queued": "邮件排队",
    "sent": "已发送",
    "failed": "邮件失败",
}

EVENT_TO_STATUS = {
    "recommended": "prospect",
    "assigned": "prospect",
    "sent": "\u5df2\u5efa\u8054",
    "pending_reply": "\u5f85\u56de\u590d",
    "contacted": "\u6c9f\u901a\u4e2d",
    "replied": "\u6c9f\u901a\u4e2d",
    "communicating": "\u6c9f\u901a\u4e2d",
    "confirmed": "\u6c9f\u901a\u4e2d",
    "sample_shipped": "sample_shipped",
    "sample_delivered": "sample_delivered",
    "partnered": "ad_authorized",
    "ad_authorized": "ad_authorized",
    "ad_running": "ad_running",
    "video_published": "video_published",
    "dropped": "dropped",
}

PROFILE_OVERWRITE_FIELDS = (
    "display_name",
    "profile_url",
    "bio",
    "followers_raw",
    "followers_count",
    "email",
    "has_email",
    "external_links_json",
    "source_video_url",
    "source_video_title",
    "source_video_description",
    "search_keyword",
    "source",
    "avatar_url",
    "shop_profile_url",
    "lead_status",
    "tiktok_shop_json",
    "profile_snapshot_json",
    "primary_product_category",
    "primary_product_fit_score",
    "recommendation_status",
    "recommended_product_type",
    "recommended_collab_type",
    "outreach_priority",
    "recommendation_score",
    "recommendation_reason",
    "risk_summary",
    "next_action",
    "review_required",
    "review_status",
    "fit_evidence_source_json",
    "matched_keywords_json",
    "evidence_strength",
    "evidence_text_json",
    "risk_tags_json",
    "positive_tags_json",
    "content_format_status",
    "score_version",
    "tag_version",
    "rec_version",
    "scored_at",
    "tagged_at",
    "recommended_at",
    "collected_at",
    "last_seen_at",
)


def normalize_handle(value: Any) -> str:
    return str(value or "").strip().lstrip("@").strip().lower()


def normalize_platform(value: Any) -> str:
    text_value = str(value or "tiktok").strip().lower().replace("-", "_")
    if text_value in {"", "unknown", "tiktok_shop", "shop"}:
        return "tiktok"
    return text_value


def normalize_url(value: Any) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    return text_value.rstrip("/").lower()


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def canonical_source_type(platform: Any = None, source: Any = None) -> str:
    raw_source = str(source or "").strip().lower()
    raw_platform = str(platform or "").strip().lower()
    if raw_source in SOURCE_TYPES:
        return raw_source
    if raw_platform == "tiktok_shop" or raw_source == SOURCE_SHOP or "tiktok_shop" in raw_source:
        return SOURCE_TIKTOK_SHOP
    if raw_source in {SOURCE_X9_LEADS, "x9_leads", "tiktok_video"}:
        return SOURCE_TIKTOK_VIDEO
    if raw_source in {SOURCE_TABLE_IMPORT, "bd", "bd_import", "staff_note", "manual_bd", "weekly_import"}:
        return SOURCE_BD
    classified = classify_source(raw_platform, raw_source)
    if classified == SOURCE_SHOP:
        return SOURCE_TIKTOK_SHOP
    if classified == SOURCE_TABLE_IMPORT:
        return SOURCE_BD
    if classified == SOURCE_X9_LEADS:
        return SOURCE_TIKTOK_VIDEO
    return SOURCE_OTHER


def _truthy_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(text_value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _db_datetime(value: Any) -> datetime | None:
    dt = _as_datetime(value)
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _latest(*values: Any) -> datetime | None:
    dates = [d for d in (_db_datetime(v) for v in values) if d is not None]
    if not dates:
        return None
    return max(dates)


def find_matching_creator(
    db: Session,
    *,
    platform: Any = None,
    handle: Any = None,
    email: Any = None,
    profile_url: Any = None,
    shop_profile_url: Any = None,
    exclude_id: str | None = None,
) -> Creator | None:
    platform_key = normalize_platform(platform)
    handle_key = normalize_handle(handle)
    if handle_key:
        return db.scalars(
            select(Creator)
            .where(func.lower(func.trim(Creator.platform)).in_([platform_key, "tiktok_shop"]))
            .where(func.lower(func.trim(Creator.handle)).in_([handle_key, f"@{handle_key}"]))
            .where(Creator.id != exclude_id if exclude_id else text("1=1"))
            .limit(1)
        ).first()
    clauses = []
    email_key = normalize_email(email)
    if email_key:
        clauses.append(func.lower(func.trim(Creator.email)) == email_key)
    for column, value in (
        (Creator.profile_url, profile_url),
        (Creator.shop_profile_url, shop_profile_url),
    ):
        url_key = normalize_url(value)
        if url_key:
            clauses.append(func.lower(func.trim(column)).in_([url_key, f"{url_key}/"]))
    if not clauses:
        return None
    q = select(Creator).where(or_(*clauses))
    if exclude_id:
        q = q.where(Creator.id != exclude_id)
    return db.scalars(q.limit(1)).first()


def find_existing_for_payload(db: Session, platform: Any, handle: Any, payload: dict[str, Any] | None = None) -> Creator | None:
    payload = payload or {}
    creator = payload.get("creator") if isinstance(payload.get("creator"), dict) else {}
    shop = payload.get("tiktok_shop") if isinstance(payload.get("tiktok_shop"), dict) else {}
    list_item = shop.get("list_item") if isinstance(shop.get("list_item"), dict) else {}
    return find_matching_creator(
        db,
        platform=platform,
        handle=handle,
        email=creator.get("email") or _first_list_value(creator.get("emails")),
        profile_url=creator.get("profile_url"),
        shop_profile_url=creator.get("shop_profile_url") or shop.get("source_page_url") or list_item.get("source_page_url"),
    )


def _first_list_value(value: Any) -> Any:
    if isinstance(value, list):
        return next((item for item in value if str(item or "").strip()), None)
    return value


def record_creator_source(
    db: Session,
    creator: Creator,
    *,
    source_type: str,
    actor_user_id: str | None = None,
    raw_observation_id: str | None = None,
    worker_id: str | None = None,
    account_id: str | None = None,
    observed_at: Any = None,
    metadata: dict[str, Any] | None = None,
) -> CreatorSource:
    source_type = canonical_source_type(creator.platform, source_type)
    actor_clause = (
        CreatorSource.actor_user_id.is_(None)
        if actor_user_id is None
        else CreatorSource.actor_user_id == actor_user_id
    )
    existing = db.scalars(
        select(CreatorSource)
        .where(CreatorSource.creator_id == creator.id)
        .where(CreatorSource.source_type == source_type)
        .where(actor_clause)
        .limit(1)
    ).first()
    seen_at = _db_datetime(observed_at) or datetime.now()
    if existing is None:
        existing = CreatorSource(
            id=new_id("src"),
            creator_id=creator.id,
            department_code=creator.department_code or DEFAULT_DEPARTMENT,
            source_type=source_type,
            platform=creator.platform,
            handle=creator.handle,
            actor_user_id=actor_user_id,
            first_seen_at=seen_at,
        )
        db.add(existing)
    existing.department_code = creator.department_code or existing.department_code or DEFAULT_DEPARTMENT
    existing.platform = creator.platform
    existing.handle = creator.handle
    existing.raw_observation_id = raw_observation_id or existing.raw_observation_id
    existing.worker_id = worker_id or existing.worker_id
    existing.account_id = account_id or existing.account_id
    first_seen = _db_datetime(existing.first_seen_at)
    last_seen = _db_datetime(existing.last_seen_at)
    if first_seen is None or seen_at < first_seen:
        existing.first_seen_at = seen_at
    if last_seen is None or seen_at > last_seen:
        existing.last_seen_at = seen_at
    if metadata:
        existing.metadata_json = dumps_json(metadata)
    db.flush()
    return existing


def create_outreach_event(
    db: Session,
    creator: Creator,
    *,
    event_type: str,
    actor_user_id: str | None = None,
    owner_bd: str | None = None,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
    event_at: Any = None,
) -> CreatorOutreachEvent:
    event_type = str(event_type or "").strip().lower()
    if event_type not in OUTREACH_EVENT_ORDER:
        raise ValueError(f"unknown outreach event: {event_type}")
    event = CreatorOutreachEvent(
        id=new_id("oev"),
        creator_id=creator.id,
        department_code=creator.department_code or DEFAULT_DEPARTMENT,
        event_type=event_type,
        actor_user_id=actor_user_id,
        owner_bd=owner_bd,
        note=note,
        metadata_json=dumps_json(metadata or {}) if metadata else None,
        event_at=_as_datetime(event_at) or datetime.now(timezone.utc),
    )
    db.add(event)
    if owner_bd and (event_type == "assigned" or not creator.owner_bd):
        creator.owner_bd = owner_bd
    status = EVENT_TO_STATUS.get(event_type)
    if status and (event_type not in {"recommended", "assigned"} or not (creator.current_status or "").strip()):
        creator.current_status = status
    from .followup_service import apply_outreach_event_followups  # noqa: WPS433

    apply_outreach_event_followups(
        db,
        creator=creator,
        event_type=event_type,
        actor_user_id=actor_user_id,
        metadata=metadata,
    )
    db.flush()
    return event


def has_outreach_activity(db: Session, creator_id: str) -> bool:
    if db.scalar(select(func.count(CreatorOutreachEvent.id)).where(CreatorOutreachEvent.creator_id == creator_id)):
        return True
    return bool(
        db.scalar(
            select(func.count(OutreachEmail.id))
            .where(OutreachEmail.creator_id == creator_id)
            .where(OutreachEmail.status.notin_(["cancelled"]))
        )
    )


def recommendation_visibility(db: Session, creator: Creator) -> dict[str, Any]:
    owner = (creator.owner_bd or "").strip()
    has_events = has_outreach_activity(db, creator.id)
    if owner or has_events:
        return {
            "availability": "progressed" if has_events else "assigned",
            "available_to_claim": False,
            "owner_bd": owner or None,
        }
    return {"availability": "available", "available_to_claim": True, "owner_bd": None}


def _creator_sort_key(c: Creator) -> tuple[int, datetime]:
    return (
        1 if (c.owner_bd or "").strip() else 0,
        _latest(c.updated_at, c.last_seen_at, c.collected_at, c.created_at) or datetime.min,
    )


def _copy_profile_fields(target: Creator, source: Creator) -> None:
    source_newer = (_latest(source.updated_at, source.last_seen_at, source.collected_at) or datetime.min) >= (
        _latest(target.updated_at, target.last_seen_at, target.collected_at) or datetime.min
    )
    for field in PROFILE_OVERWRITE_FIELDS:
        value = getattr(source, field, None)
        if not _truthy_value(value):
            continue
        current = getattr(target, field, None)
        if not _truthy_value(current) or source_newer:
            setattr(target, field, value)
    if not (target.owner_bd or "").strip() and (source.owner_bd or "").strip():
        target.owner_bd = source.owner_bd
    if not (target.store_assigned or "").strip() and (source.store_assigned or "").strip():
        target.store_assigned = source.store_assigned


def normalize_creators(db: Session, *, dry_run: bool = False, limit: int = 5000) -> dict[str, Any]:
    creators = list(db.scalars(select(Creator).limit(max(1, min(int(limit or 5000), 50000)))).all())
    groups: dict[tuple[str, str], list[Creator]] = defaultdict(list)
    for creator in creators:
        handle = normalize_handle(creator.handle)
        if handle:
            groups[(normalize_platform(creator.platform), handle)].append(creator)
    duplicate_groups = [items for items in groups.values() if len(items) > 1]
    merged = 0
    moved = Counter()
    samples: list[dict[str, Any]] = []
    for items in duplicate_groups:
        canonical = sorted(items, key=_creator_sort_key, reverse=True)[0]
        for duplicate in items:
            if duplicate.id == canonical.id:
                continue
            samples.append({"from": duplicate.id, "to": canonical.id, "handle": duplicate.handle})
            if not dry_run:
                _copy_profile_fields(canonical, duplicate)
                for model in (CreatorSource, CreatorOutreachEvent, CreatorRecommendation, OutreachEmail, ReviewTask):
                    rows = list(db.scalars(select(model).where(model.creator_id == duplicate.id)).all())
                    for row in rows:
                        row.creator_id = canonical.id
                        moved[model.__tablename__] += 1
                db.delete(duplicate)
            merged += 1
    if not dry_run:
        db.commit()
    return {
        "ok": True,
        "dry_run": dry_run,
        "duplicate_groups": len(duplicate_groups),
        "merged": merged,
        "moved": dict(moved),
        "samples": samples[:20],
    }


def backfill_creator_sources(db: Session, *, limit: int = 50000) -> dict[str, Any]:
    rows = list(db.scalars(select(Creator).limit(max(1, min(int(limit or 50000), 200000)))).all())
    counts = Counter()
    for creator in rows:
        source_type = creator_source_type(creator)
        if source_type != SOURCE_OTHER:
            for legacy_other in db.scalars(
                select(CreatorSource)
                .where(CreatorSource.creator_id == creator.id)
                .where(CreatorSource.source_type == SOURCE_OTHER)
            ).all():
                legacy_other.source_type = source_type
        record_creator_source(
            db,
            creator,
            source_type=source_type,
            observed_at=creator.collected_at or creator.created_at,
            metadata={"backfill": "creators.source"},
        )
        counts[source_type] += 1
    db.commit()
    return {"ok": True, "processed": len(rows), "source_counts": dict(counts)}


def creator_source_type(creator: Creator) -> str:
    source_type = canonical_source_type(creator.platform, creator.source)
    if source_type != SOURCE_OTHER:
        return source_type
    if (creator.owner_bd or "").strip() or (creator.current_status or "").strip():
        return SOURCE_BD
    if normalize_platform(creator.platform) == "tiktok":
        return SOURCE_TIKTOK_VIDEO
    return SOURCE_TIKTOK_VIDEO


_TIKTOK_HANDLE_URL_RE = re.compile(r"tiktok\.com/@(?P<handle>[A-Za-z0-9._-]+)", re.IGNORECASE)


def _handle_from_legacy_row(row: dict[str, Any]) -> str:
    handle = normalize_handle(row.get("handle"))
    if handle:
        return handle
    match = _TIKTOK_HANDLE_URL_RE.search(str(row.get("profile_url") or ""))
    return normalize_handle(match.group("handle")) if match else ""


def _event_from_legacy_status(status: Any) -> str | None:
    value = str(status or "").strip().lower()
    if not value:
        return None
    value = value.replace(" ", "_").replace("-", "_")
    mapping = {
        "recommended": "recommended",
        "prospect": "recommended",
        "assigned": "assigned",
        "contacted": "sent",
        "sent": "sent",
        "已建联": "sent",
        "已联系": "sent",
        "pending_reply": "pending_reply",
        "待回复": "pending_reply",
        "replied": "replied",
        "已回复": "replied",
        "confirmed": "replied",
        "已确认": "replied",
        "sample_shipped": "sample_shipped",
        "sample_in_transit": "sample_shipped",
        "shipping_follow_up": "sample_shipped",
        "已寄样": "sample_shipped",
        "运输中": "sample_shipped",
        "sample_delivered": "sample_delivered",
        "delivered": "sample_delivered",
        "样品签收": "sample_delivered",
        "partnered": "partnered",
        "ad_authorized": "partnered",
        "deal_closed": "partnered",
        "合作": "partnered",
        "已合作": "partnered",
        "video_published": "video_published",
        "已发视频": "video_published",
        "dropped": "dropped",
        "放弃": "dropped",
        "已放弃": "dropped",
    }
    return mapping.get(value)


def _legacy_source_type(table: str, row: dict[str, Any]) -> str:
    source = row.get("source")
    if source:
        source_type = canonical_source_type(row.get("platform"), source)
        if source_type != SOURCE_OTHER:
            return source_type
    if table == "tk_creators":
        return SOURCE_TIKTOK_VIDEO
    if row.get("owner_bd") or row.get("current_status") or str(row.get("source") or "").lower() in {"weekly_import", "bd"}:
        return SOURCE_BD
    return canonical_source_type(row.get("platform"), source)


def _legacy_event_exists(db: Session, creator_id: str, event_type: str) -> bool:
    return bool(db.scalars(
        select(CreatorOutreachEvent.id)
        .where(CreatorOutreachEvent.creator_id == creator_id)
        .where(CreatorOutreachEvent.event_type == event_type)
        .limit(1)
    ).first())


def _copy_legacy_row_to_creator(creator: Creator, row: dict[str, Any], *, source_type: str) -> None:
    text_fields = (
        "display_name",
        "profile_url",
        "bio",
        "followers_raw",
        "email",
        "external_links_json",
        "source_video_url",
        "source_video_title",
        "source_video_description",
        "search_keyword",
        "store_assigned",
        "notes",
    )
    for field in text_fields:
        value = row.get(field)
        if _truthy_value(value):
            setattr(creator, field, str(value).strip())
    followers_count = row.get("followers_count")
    if followers_count is None:
        followers_count = row.get("followers")
    if _truthy_value(followers_count):
        try:
            creator.followers_count = int(float(followers_count))
        except (TypeError, ValueError):
            pass
    if creator.email:
        creator.email = creator.email.strip().lower()
        creator.has_email = 1
    elif creator.has_email is None:
        creator.has_email = 0
    for field in (
        "recommendation_status",
        "recommended_product_type",
        "recommended_collab_type",
        "outreach_priority",
        "recommendation_reason",
        "risk_summary",
        "next_action",
        "review_status",
        "fit_level",
        "priority_level",
        "queue_type",
        "primary_product_category",
    ):
        value = row.get(field)
        if _truthy_value(value) and not _truthy_value(getattr(creator, field, None)):
            setattr(creator, field, value)
    for field in ("collected_at", "last_seen_at"):
        value = _as_datetime(row.get(field))
        if value is not None:
            setattr(creator, field, value)
    owner = str(row.get("owner_bd") or "").strip()
    if owner and (source_type == SOURCE_BD or not (creator.owner_bd or "").strip()):
        creator.owner_bd = owner
    status = str(row.get("current_status") or "").strip()
    if status and (source_type == SOURCE_BD or not (creator.current_status or "").strip()):
        creator.current_status = status
    if not creator.profile_url and creator.handle:
        creator.profile_url = f"https://www.tiktok.com/@{creator.handle}"
    creator.source = source_type if source_type != SOURCE_OTHER else (creator.source or SOURCE_OTHER)


def backfill_legacy_creator_tables(db: Session, *, limit: int = 200000) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    for table in ("creator", "tk_creators"):
        if not _table_exists(db, table):
            continue
        cols = _columns(db, table)
        wanted = [
            "id", "platform", "handle", "profile_url", "display_name", "bio", "followers", "followers_raw",
            "followers_count", "email", "has_email", "external_links_json", "source_video_url",
            "source_video_title", "source_video_description", "search_keyword", "current_status",
            "store_assigned", "owner_bd", "notes", "source", "collected_at", "last_seen_at",
            "recommendation_status", "recommended_product_type", "recommended_collab_type", "outreach_priority",
            "recommendation_reason", "risk_summary", "next_action", "review_status", "fit_level",
            "priority_level", "queue_type", "primary_product_category",
        ]
        select_cols = [f"{col} AS {col}" for col in wanted if col in cols]
        if not select_cols:
            continue
        rows = db.execute(text(f"SELECT {', '.join(select_cols)} FROM {table} LIMIT :limit"), {"limit": limit}).mappings()
        for raw_row in rows:
            row = dict(raw_row)
            handle = _handle_from_legacy_row(row)
            if not handle:
                counts[f"{table}_skipped_no_handle"] += 1
                continue
            platform = normalize_platform(row.get("platform") or "tiktok")
            source_type = _legacy_source_type(table, row)
            creator = find_matching_creator(
                db,
                platform=platform,
                handle=handle,
                email=row.get("email"),
                profile_url=row.get("profile_url"),
            )
            if creator is None:
                creator = Creator(id=creator_id_for(platform, handle), platform=platform, handle=handle, department_code=DEFAULT_DEPARTMENT)
                db.add(creator)
                counts[f"{table}_inserted"] += 1
            else:
                counts[f"{table}_updated"] += 1
            _copy_legacy_row_to_creator(creator, row, source_type=source_type)
            record_creator_source(
                db,
                creator,
                source_type=source_type,
                observed_at=row.get("collected_at") or row.get("last_seen_at"),
                metadata={"backfill": table, "legacy_id": row.get("id")},
            )
            owner = str(row.get("owner_bd") or "").strip() or None
            event_type = _event_from_legacy_status(row.get("current_status"))
            if owner and event_type is None and not _legacy_event_exists(db, creator.id, "assigned"):
                create_outreach_event(
                    db,
                    creator,
                    event_type="assigned",
                    owner_bd=owner,
                    metadata={"backfill": table, "legacy_id": row.get("id")},
                    event_at=row.get("last_seen_at") or row.get("collected_at"),
                )
            if event_type and not _legacy_event_exists(db, creator.id, event_type):
                create_outreach_event(
                    db,
                    creator,
                    event_type=event_type,
                    owner_bd=owner,
                    metadata={"backfill": table, "legacy_id": row.get("id"), "legacy_status": row.get("current_status")},
                    event_at=row.get("last_seen_at") or row.get("collected_at"),
                )
            counts[f"{table}_{source_type}"] += 1
        db.commit()
    return {"ok": True, **dict(counts)}


def ensure_creator_sources_backfilled(db: Session) -> None:
    """Idempotently seed source facts for historical creator rows.

    New captures write creator_sources during post-processing. Existing data
    needs a one-time compatibility backfill so dashboards can split Shop,
    video, and BD without counting raw observations.
    """

    creator_count = int(db.scalar(select(func.count()).select_from(Creator)) or 0)
    if creator_count == 0:
        return
    source_count = int(db.scalar(select(func.count()).select_from(CreatorSource)) or 0)
    if source_count < creator_count:
        backfill_creator_sources(db)


def _table_exists(db: Session, table: str) -> bool:
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        return bool(db.execute(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table"), {"table": table}).first())
    return bool(db.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:table"
    ), {"table": table}).first())


def _columns(db: Session, table: str) -> set[str]:
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        return {row[1] for row in db.execute(text(f"PRAGMA table_info({table})"))}
    return {row[0] for row in db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=:table"
    ), {"table": table})}


def _int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def migrate_staff_note_bd_stats(db: Session) -> dict[str, Any]:
    if not _table_exists(db, "staff"):
        return {"ok": True, "processed": 0, "upserted": 0, "reason": "staff_table_missing"}
    cols = _columns(db, "staff")
    select_cols = []
    for col in ("id", "name", "role", "note", "department_code"):
        select_cols.append(f"{col} AS {col}" if col in cols else f"NULL AS {col}")
    rows = db.execute(text("SELECT " + ", ".join(select_cols) + " FROM staff")).mappings().all()
    upserted = 0
    for row in rows:
        try:
            note = json.loads(row.get("note") or "{}")
        except (TypeError, ValueError):
            note = {}
        if not isinstance(note, dict):
            continue
        contacted = _int_value(note.get("contacted"))
        confirmed = _int_value(note.get("confirmed"))
        samples = _int_value(note.get("samples"))
        videos = _int_value(note.get("videos"))
        if not any((contacted, confirmed, samples, videos)):
            continue
        owner = str(row.get("name") or "未分配").strip() or "未分配"
        month = str(note.get("month") or "").strip()
        staff_id = str(row.get("id") or owner)
        dept = normalize_department_code(row.get("department_code"), default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT
        note_hash = hashlib.sha1(str(row.get("note") or "").encode("utf-8")).hexdigest()
        existing = db.scalars(
            select(BdMonthlyStat)
            .where(BdMonthlyStat.department_code == dept)
            .where(BdMonthlyStat.owner_name == owner)
            .where(BdMonthlyStat.month == month)
            .where(BdMonthlyStat.source_staff_id == staff_id)
            .limit(1)
        ).first()
        if existing is None:
            existing = BdMonthlyStat(
                id=new_id("bdm"),
                department_code=dept,
                owner_name=owner,
                month=month,
                source_staff_id=staff_id,
            )
            db.add(existing)
        existing.role = row.get("role") or ""
        existing.contacted = contacted
        existing.confirmed = confirmed
        existing.samples = samples
        existing.videos = videos
        existing.source_note_hash = note_hash
        existing.metadata_json = dumps_json({"source": "staff.note"})
        upserted += 1
    db.commit()
    return {"ok": True, "processed": len(rows), "upserted": upserted}


def import_bd_creators(
    db: Session,
    rows: Iterable[dict[str, Any]],
    *,
    actor_user_id: str | None,
    department_code: str | None,
) -> dict[str, Any]:
    dept = normalize_department_code(department_code, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT
    inserted = updated = 0
    for raw in rows:
        handle = normalize_handle(raw.get("handle"))
        platform = normalize_platform(raw.get("platform") or "tiktok")
        email = normalize_email(raw.get("email"))
        profile_url = raw.get("profile_url")
        shop_profile_url = raw.get("shop_profile_url")
        creator = find_matching_creator(
            db,
            platform=platform,
            handle=handle,
            email=email,
            profile_url=profile_url,
            shop_profile_url=shop_profile_url,
        )
        if creator is None:
            if not handle:
                continue
            creator = Creator(id=creator_id_for(platform, handle), platform=platform, handle=handle, department_code=dept)
            db.add(creator)
            inserted += 1
        else:
            updated += 1
        creator.department_code = dept
        for field in ("display_name", "profile_url", "bio", "email", "shop_profile_url", "notes", "store_assigned"):
            value = raw.get(field)
            if _truthy_value(value):
                setattr(creator, field, str(value).strip())
        owner = str(raw.get("owner_bd") or raw.get("bd_owner") or raw.get("owner") or "").strip()
        if owner:
            creator.owner_bd = owner
        status = str(raw.get("current_status") or "").strip()
        if status:
            creator.current_status = status
        creator.source = SOURCE_BD
        creator.collected_at = _as_datetime(raw.get("collected_at")) or datetime.now(timezone.utc)
        record_creator_source(
            db,
            creator,
            source_type=SOURCE_BD,
            actor_user_id=actor_user_id,
            observed_at=creator.collected_at,
            metadata={"source": "bd_import"},
        )
        if owner:
            create_outreach_event(
                db,
                creator,
                event_type="assigned",
                actor_user_id=actor_user_id,
                owner_bd=owner,
                metadata={"source": "bd_import"},
            )
    db.commit()
    return {"ok": True, "inserted": inserted, "updated": updated}


def _stage_rank(event_type: str | None) -> int:
    try:
        return OUTREACH_EVENT_ORDER.index(str(event_type))
    except ValueError:
        return -1


def _table_row_count(db: Session, table: str, department_code: str | None = None) -> int:
    inspector = inspect(db.bind)
    if table not in inspector.get_table_names():
        return 0
    columns = {col["name"] for col in inspector.get_columns(table)}
    if department_code and "department_code" in columns:
        if department_code == DEFAULT_DEPARTMENT:
            stmt = text(f"SELECT count(*) FROM {table} WHERE department_code = :dept OR department_code IS NULL OR department_code = ''")
        else:
            stmt = text(f"SELECT count(*) FROM {table} WHERE department_code = :dept")
        return int(db.execute(stmt, {"dept": department_code}).scalar() or 0)
    return int(db.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)


def cumulative_creator_totals(db: Session, department_code: str | None = None) -> dict[str, int]:
    dept = normalize_department_code(department_code, default=None) if department_code else None
    processed_rows = _table_row_count(db, "creators", dept)
    legacy_creator_rows = _table_row_count(db, "creator", dept)
    legacy_tk_rows = _table_row_count(db, "tk_creators", dept)
    raw_rows = _table_row_count(db, "raw_observations", dept)
    collection_total = processed_rows + legacy_creator_rows + legacy_tk_rows + raw_rows
    return {
        "total_creators": collection_total,
        "collection_channel_rows_total": collection_total,
        "processed_rows_total": processed_rows,
        "legacy_creator_rows_total": legacy_creator_rows,
        "legacy_tk_creator_rows_total": legacy_tk_rows,
        "raw_observations_total": raw_rows,
    }


def _raw_collected_trend(db: Session, department_code: str | None, day_keys: list[str]) -> dict[str, int]:
    if not day_keys or not _table_exists(db, "raw_observations"):
        return {}
    params: dict[str, Any] = {
        "start_date": day_keys[0],
        "end_date": (date.fromisoformat(day_keys[-1]) + timedelta(days=1)).isoformat(),
    }
    date_expr = "DATE(NULLIF(CAST(collected_at AS TEXT), ''))"
    clauses = [
        f"{date_expr} >= :start_date",
        f"{date_expr} < :end_date",
    ]
    for index, status in enumerate(RAW_QUEUE_LEAD_STATUSES):
        key = f"queue_status_{index}"
        params[key] = status
        clauses.append(f"COALESCE(lead_status, '') != :{key}")
    if department_code:
        params["department_code"] = department_code
        if department_code == DEFAULT_DEPARTMENT:
            clauses.append("(department_code = :department_code OR department_code IS NULL OR department_code = '')")
        else:
            clauses.append("department_code = :department_code")
    sql = f"""
        SELECT {date_expr} AS day, COUNT(*) AS count
        FROM raw_observations
        WHERE {" AND ".join(clauses)}
        GROUP BY day
    """
    return {str(day): int(count or 0) for day, count in db.execute(text(sql), params).all()}


def _creator_display_name(creator: Creator | None, creator_id: str | None) -> str:
    if creator is None:
        return str(creator_id or "未知达人")
    return (
        str(creator.display_name or "").strip()
        or str(creator.handle or "").strip()
        or str(creator_id or "未知达人")
    )


def _recent_activity_rows(
    db: Session,
    *,
    department_code: str | None,
    actor_user_id: str | None,
    limit: int = 12,
) -> list[dict[str, Any]]:
    event_q = select(CreatorOutreachEvent)
    email_q = select(OutreachEmail).where(OutreachEmail.status.in_(tuple(EMAIL_EVENT_LABELS)))
    if department_code:
        event_q = event_q.where(CreatorOutreachEvent.department_code == department_code)
        email_q = email_q.where(OutreachEmail.department_code == department_code)
    if actor_user_id:
        event_q = event_q.where(CreatorOutreachEvent.actor_user_id == actor_user_id)
        email_q = email_q.where(OutreachEmail.created_by == actor_user_id)
    event_rows = list(db.scalars(
        event_q
        .order_by(CreatorOutreachEvent.event_at.desc(), CreatorOutreachEvent.created_at.desc())
        .limit(max(limit * 2, limit))
    ).all())
    email_rows = list(db.scalars(
        email_q
        .order_by(func.coalesce(OutreachEmail.sent_at, OutreachEmail.updated_at, OutreachEmail.created_at).desc())
        .limit(max(limit * 2, limit))
    ).all())

    creator_ids = {str(row.creator_id) for row in event_rows + email_rows if row.creator_id}
    creator_map = {
        str(creator.id): creator
        for creator in db.scalars(select(Creator).where(Creator.id.in_(creator_ids))).all()
    } if creator_ids else {}
    rows: list[dict[str, Any]] = []
    for event in event_rows:
        dt = _db_datetime(event.event_at) or _db_datetime(event.created_at) or datetime.min
        event_type = str(event.event_type or "").strip()
        label = RECENT_EVENT_LABELS.get(event_type, event_type or "事件")
        actor = str(event.owner_bd or event.actor_user_id or "系统").strip() or "系统"
        creator_name = _creator_display_name(creator_map.get(str(event.creator_id)), str(event.creator_id))
        rows.append({
            "id": f"outreach_event:{event.id}",
            "occurred_at": dt.isoformat(),
            "source": "creator_outreach_events",
            "event_type": event_type,
            "event_label": label,
            "actor": actor,
            "creator_id": str(event.creator_id),
            "creator": creator_name,
            "department_code": event.department_code,
            "title": str(event.note or "").strip() or f"{actor} 对 {creator_name} {label}",
            "_sort_at": dt,
        })
    for email in email_rows:
        dt = _db_datetime(email.sent_at) or _db_datetime(email.updated_at) or _db_datetime(email.created_at) or datetime.min
        status = str(email.status or "").strip().lower()
        label = EMAIL_EVENT_LABELS.get(status, f"邮件{status}" if status else "邮件事件")
        actor = str(email.from_email or email.created_by or "系统").strip() or "系统"
        creator_name = _creator_display_name(creator_map.get(str(email.creator_id)), str(email.creator_id))
        rows.append({
            "id": f"outreach_email:{email.id}",
            "occurred_at": dt.isoformat(),
            "source": "outreach_emails",
            "event_type": f"email_{status}" if status else "email",
            "event_label": label,
            "actor": actor,
            "creator_id": str(email.creator_id),
            "creator": creator_name,
            "department_code": email.department_code,
            "title": f"{actor} 给 {creator_name} {label}",
            "_sort_at": dt,
        })
    rows.sort(key=lambda row: row["_sort_at"], reverse=True)
    return [
        {key: value for key, value in row.items() if key != "_sort_at"}
        for row in rows[:limit]
    ]


def analytics_summary(
    db: Session,
    *,
    scope: str,
    department_code: str | None = None,
    actor_user_id: str | None = None,
    days: int = 30,
) -> dict[str, Any]:
    ensure_creator_sources_backfilled(db)
    dept = normalize_department_code(department_code, default=None) if department_code else None
    creator_q = select(Creator)
    source_q = select(CreatorSource)
    event_q = select(CreatorOutreachEvent)
    bd_q = select(BdMonthlyStat)
    if dept:
        creator_q = creator_q.where(Creator.department_code == dept)
        source_q = source_q.where(CreatorSource.department_code == dept)
        event_q = event_q.where(CreatorOutreachEvent.department_code == dept)
        bd_q = bd_q.where(BdMonthlyStat.department_code == dept)
    if actor_user_id:
        source_q = source_q.where(CreatorSource.actor_user_id == actor_user_id)
        event_q = event_q.where(CreatorOutreachEvent.actor_user_id == actor_user_id)
    creators = list(db.scalars(creator_q).all())
    sources = list(db.scalars(source_q).all())
    events = list(db.scalars(event_q).all())
    bd_stats = list(db.scalars(bd_q).all())

    creator_ids_from_sources = {s.creator_id for s in sources}
    creator_ids_from_events = {e.creator_id for e in events}
    if actor_user_id:
        visible_ids = creator_ids_from_sources | creator_ids_from_events | {c.id for c in creators if (c.owner_bd or "") == actor_user_id}
        creators = [c for c in creators if c.id in visible_ids]

    source_counts = Counter(source for source, _creator_id in {(s.source_type, s.creator_id) for s in sources})
    member_counts: dict[str, Counter] = defaultdict(Counter)
    for member, source, _creator_id in {
        (s.actor_user_id or "unassigned", s.source_type, s.creator_id)
        for s in sources
    }:
        member_counts[member][f"{source}_processed"] += 1
    event_counts = Counter(e.event_type for e in events)
    member_contacted_creators: dict[str, set[str]] = defaultdict(set)
    for e in events:
        member = e.actor_user_id or "unassigned"
        member_counts[member][e.event_type] += 1
        if e.event_type in CONTACTED_EVENT_TYPES and e.creator_id:
            member_contacted_creators[member].add(e.creator_id)
    for member, creator_ids in member_contacted_creators.items():
        member_counts[member]["total_contacted"] += len(creator_ids)
    bd_totals = {
        "contacted": sum(row.contacted for row in bd_stats),
        "confirmed": sum(row.confirmed for row in bd_stats),
        "samples": sum(row.samples for row in bd_stats),
        "videos": sum(row.videos for row in bd_stats),
    }
    for row in bd_stats:
        member = str(row.owner_name or "unassigned").strip() or "unassigned"
        member_counts[member]["bd_history_contacted"] += int(row.contacted or 0)
        member_counts[member]["bd_history_confirmed"] += int(row.confirmed or 0)
        member_counts[member]["bd_history_samples"] += int(row.samples or 0)
        member_counts[member]["bd_history_videos"] += int(row.videos or 0)
        member_counts[member]["total_contacted"] += int(row.contacted or 0)
        member_counts[member]["confirmed"] += int(row.confirmed or 0)
        member_counts[member]["sample_shipped"] += int(row.samples or 0)
        member_counts[member]["video_published"] += int(row.videos or 0)
    cumulative = cumulative_creator_totals(db, dept)
    today = datetime.now().date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(max(1, min(days, 120)) - 1, -1, -1)]
    raw_collected_by_day = _raw_collected_trend(db, dept, day_keys)
    trend = {
        key: {
            "date": key,
            "collected": raw_collected_by_day.get(key, 0),
            "processed": 0,
            "recommended": 0,
            "sent": 0,
            "partnered": 0,
        }
        for key in day_keys
    }
    for s in sources:
        day = (_as_datetime(s.last_seen_at or s.first_seen_at or s.created_at) or datetime.min).date().isoformat()
        if day in trend:
            trend[day]["processed"] += 1
    for e in events:
        day = (_as_datetime(e.event_at or e.created_at) or datetime.min).date().isoformat()
        if day in trend and e.event_type in {"recommended", "sent", "partnered"}:
            trend[day][e.event_type] += 1

    by_department: dict[str, Counter] = defaultdict(Counter)
    for c in creators:
        by_department[c.department_code or DEFAULT_DEPARTMENT]["creators"] += 1
    for s in sources:
        by_department[s.department_code or DEFAULT_DEPARTMENT][f"{s.source_type}_processed"] += 1
    for e in events:
        by_department[e.department_code or DEFAULT_DEPARTMENT][e.event_type] += 1

    return {
        "ok": True,
        "scope": {
            "type": scope,
            "department_code": dept,
            "actor_user_id": actor_user_id,
        },
        "summary": {
            "total_creators": cumulative["total_creators"],
            "processed_creators": len(creators),
            "recommended": sum(1 for c in creators if c.recommendation_status not in {None, "", "hold", "not_recommended_now", "no_contact_info"}),
            "assigned": sum(1 for c in creators if (c.owner_bd or "").strip()),
            "outreach_sent": event_counts.get("sent", 0),
            "pending_reply": event_counts.get("pending_reply", 0),
            "replied": event_counts.get("replied", 0),
            "sample_shipped": event_counts.get("sample_shipped", 0),
            "partnered": event_counts.get("partnered", 0),
            "total_contacted": sum(len(ids) for ids in member_contacted_creators.values()) + bd_totals["contacted"],
            "raw_observations_are_excluded": True,
            "collection_channel_rows_total": cumulative["collection_channel_rows_total"],
            "business_with_bd_history_total": cumulative["collection_channel_rows_total"] + bd_totals["contacted"],
            "raw_observations_total": cumulative["raw_observations_total"],
            "legacy_creator_rows_total": cumulative["legacy_creator_rows_total"],
            "legacy_tk_creator_rows_total": cumulative["legacy_tk_creator_rows_total"],
            "bd_history": bd_totals,
        },
        "source_counts": [
            {"name": source, "count": source_counts.get(source, 0)}
            for source in (SOURCE_TIKTOK_SHOP, SOURCE_TIKTOK_VIDEO, SOURCE_BD)
        ],
        "event_counts": [{"name": name, "count": event_counts.get(name, 0)} for name in OUTREACH_EVENT_ORDER],
        "recent_events": _recent_activity_rows(
            db,
            department_code=dept,
            actor_user_id=actor_user_id,
            limit=12,
        ),
        "members": [
            {"member": member, **dict(counts)}
            for member, counts in sorted(member_counts.items(), key=lambda item: (-sum(item[1].values()), item[0]))
        ],
        "departments": [
            {"department_code": dept_code, **dict(counts)}
            for dept_code, counts in sorted(by_department.items(), key=lambda item: (-item[1].get("creators", 0), item[0]))
        ],
        "trend": list(trend.values()),
    }
