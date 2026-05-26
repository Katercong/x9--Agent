from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Iterable

from sqlalchemy import String, case, cast, func, or_, select, update
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.creator_source import CreatorSource
from ..models.raw_observation import RawObservation
from ..services.departments import department_where
from ..utils import stats_cache
from ..utils.json_utils import loads_json_list
from ..utils.source_classify import (
    SOURCE_OTHER as SRC_OTHER,
    SOURCE_SHOP as SRC_SHOP,
    SOURCE_TABLE_IMPORT as SRC_TABLE_IMPORT,
    SOURCE_X9_LEADS as SRC_X9_LEADS,
    classify_source,
)

UNASSIGNED_ACTOR = "__unassigned__"
SOURCE_KEYS = (SRC_SHOP, SRC_X9_LEADS, SRC_TABLE_IMPORT, SRC_OTHER)
SHOP_QUEUE_LEAD_STATUS = "shop_list_seen"
SHOP_QUEUE_CLEARED_STATUS = "shop_queue_cleared"
SOURCE_VIDEO_SEED_PATTERN = '%"lead_status":"source_video_seen"%'
STATS_CACHE_TTL_SECONDS = 60.0


def _iso_or_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_date(value: Any):
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text.split(".")[0], "%Y-%m-%d %H:%M:%S").date()
        except ValueError:
            return None


def _raw_day(row: Any):
    return _as_date(getattr(row, "collected_at", None)) or _as_date(getattr(row, "created_at", None))


def _empty_daily(days: int = 7) -> dict[str, int]:
    today = datetime.now().date()
    return {(today - timedelta(days=i)).isoformat(): 0 for i in range(days - 1, -1, -1)}


def _empty_source_bucket(days: int = 7) -> dict[str, Any]:
    return {
        "total": 0,
        "today": 0,
        "daily": _empty_daily(days),
        "queued_total": 0,
        "ingested_total": 0,
        "last_collected_at": None,
    }


def empty_source_stats(days: int = 7) -> dict[str, dict[str, Any]]:
    return {key: _empty_source_bucket(days) for key in SOURCE_KEYS}


def empty_collection_stats() -> dict[str, Any]:
    return {
        "scope": "user",
        "total": 0,
        "today": 0,
        "shop_total": 0,
        "shop_today": 0,
        "shop_detail_total": 0,
        "valid_detail_total": 0,
        "queued_total": 0,
        "ingested_total": 0,
        "last_collected_at": None,
        "user_status": "offline",
        "with_email": 0,
        "with_links": 0,
        "with_gmv": 0,
        "sources": empty_source_stats(),
    }


def _apply_actor_filter(q, model, actor_filter: str | None):
    if actor_filter is None:
        return q
    column = getattr(model, "actor_user_id")
    if actor_filter == UNASSIGNED_ACTOR:
        return q.where(or_(column.is_(None), column == ""))
    return q.where(column == actor_filter)


def _exclude_source_video_seed_rows(q):
    return q.where(
        or_(
            RawObservation.lead_status.is_(None),
            ~RawObservation.lead_status.in_(["source_video_seen", SHOP_QUEUE_CLEARED_STATUS]),
        )
    )


def clear_stale_shop_queue_rows(
    db: Session,
    *,
    cutoff: datetime | None = None,
    batch_size: int = 1000,
    safety_cap: int = 100_000,
) -> dict[str, Any]:
    """Clear stale TikTok Shop list-queue rows without deleting raw audit blobs.

    `shop_list_seen` rows are operational queue markers. Detail/profile rows and
    rows already tied to `creator_sources` are left untouched.
    """
    cutoff = cutoff or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    batch_size = max(1, min(int(batch_size or 1000), 5000))
    safety_cap = max(batch_size, int(safety_cap or 100_000))
    ts = func.coalesce(RawObservation.collected_at, RawObservation.created_at)
    ts_text = func.coalesce(cast(RawObservation.collected_at, String), cast(RawObservation.created_at, String))
    cutoff_key = cutoff.strftime("%Y-%m-%d")
    referenced_raw_ids = select(CreatorSource.raw_observation_id).where(
        CreatorSource.raw_observation_id.is_not(None),
        CreatorSource.raw_observation_id != "",
    )
    cleared = 0
    batches = 0
    while cleared < safety_cap:
        victim_q = (
            select(RawObservation.id)
            .where(
                RawObservation.platform == "tiktok_shop",
                RawObservation.lead_status == SHOP_QUEUE_LEAD_STATUS,
                ts_text < cutoff_key,
                ~RawObservation.id.in_(referenced_raw_ids),
            )
            .order_by(ts.asc(), RawObservation.id.asc())
            .limit(min(batch_size, safety_cap - cleared))
        )
        victim_ids = [row[0] for row in db.execute(victim_q).all()]
        if not victim_ids:
            break
        result = db.execute(
            update(RawObservation)
            .where(RawObservation.id.in_(victim_ids))
            .values(lead_status=SHOP_QUEUE_CLEARED_STATUS)
        )
        db.commit()
        rows = int(result.rowcount or len(victim_ids))
        cleared += rows
        batches += 1
        if rows < len(victim_ids):
            break
    if cleared:
        stats_cache.clear()
    return {
        "ok": True,
        "cleared": cleared,
        "batches": batches,
        "cutoff": cutoff.isoformat(),
        "lead_status": SHOP_QUEUE_CLEARED_STATUS,
    }


def _source_bucket_from_creator_source(source_type: str | None, platform: str | None, source: str | None) -> str:
    if source_type == "tiktok_shop":
        return SRC_SHOP
    if source_type == "tiktok_video":
        return SRC_X9_LEADS
    if source_type == "bd":
        return SRC_TABLE_IMPORT
    return classify_source(platform, source)


def _load_shop_metrics(creator: Creator) -> dict[str, Any]:
    if not creator.tiktok_shop_json:
        return {}
    try:
        parsed = json.loads(creator.tiktok_shop_json)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _has_gmv(creator: Creator) -> bool:
    metrics = _load_shop_metrics(creator)
    return bool(str(metrics.get("gmv_raw") or "").strip())


def _has_detail_capture(creator: Creator) -> bool:
    metrics = _load_shop_metrics(creator)
    return bool(
        creator.lead_status == "shop_profile_collected"
        or metrics.get("detail_captured")
        or str(metrics.get("detail_captured_at") or "").strip()
    )


def _has_links(creator: Creator) -> bool:
    return bool(loads_json_list(creator.external_links_json))


def _source_contacts_from_creators(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
) -> dict[str, dict[str, int]]:
    contacts: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, str, str]] = set()

    if actor_filter is None:
        q = select(Creator, Creator.source)
        where_department = department_where(Creator, department_code)
        if where_department is not None:
            q = q.where(where_department)
        rows = ((creator, None, source) for creator, source in db.execute(q).all())
    else:
        q = select(Creator, CreatorSource.source_type, Creator.source).join(
            CreatorSource,
            CreatorSource.creator_id == Creator.id,
        )
        where_department = department_where(CreatorSource, department_code)
        if where_department is not None:
            q = q.where(where_department)
        q = _apply_actor_filter(q, CreatorSource, actor_filter)
        rows = db.execute(q).all()

    today = datetime.now().date()
    for creator, source_type, fallback_source in rows:
        bucket = _source_bucket_from_creator_source(source_type, creator.platform, fallback_source)
        actor_key = actor_filter or "all"
        key = (actor_key, bucket, creator.id)
        if key in seen:
            continue
        seen.add(key)
        stat = contacts.setdefault(bucket, {
            "total": 0,
            "with_email": 0,
            "with_links": 0,
            "with_gmv": 0,
            "valid_detail_total": 0,
            "today_total": 0,
            "today_with_email": 0,
            "today_with_links": 0,
            "today_with_gmv": 0,
        })
        has_email = bool(str(creator.email or "").strip())
        has_links = _has_links(creator)
        has_gmv = _has_gmv(creator)
        has_valid_detail = bucket == SRC_SHOP and _has_detail_capture(creator) and (has_email or has_links or has_gmv)
        is_today = _as_date(creator.collected_at) or _as_date(creator.created_at)
        is_today = is_today == today
        stat["total"] += 1
        if has_email:
            stat["with_email"] += 1
        if has_links:
            stat["with_links"] += 1
        if has_gmv:
            stat["with_gmv"] += 1
        if has_valid_detail:
            stat["valid_detail_total"] += 1
        if is_today:
            stat["today_total"] += 1
            if has_email:
                stat["today_with_email"] += 1
            if has_links:
                stat["today_with_links"] += 1
            if has_gmv:
                stat["today_with_gmv"] += 1
    return contacts


def _source_ingested_raw_counts(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    q = (
        select(
            CreatorSource.source_type,
            CreatorSource.platform,
            Creator.source,
            func.count(func.distinct(CreatorSource.raw_observation_id)),
        )
        .join(Creator, Creator.id == CreatorSource.creator_id)
        .where(CreatorSource.raw_observation_id.is_not(None), CreatorSource.raw_observation_id != "")
        .group_by(CreatorSource.source_type, CreatorSource.platform, Creator.source)
    )
    where_department = department_where(CreatorSource, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = _apply_actor_filter(q, CreatorSource, actor_filter)
    for source_type, platform, fallback_source, count in db.execute(q).all():
        bucket = _source_bucket_from_creator_source(source_type, platform, fallback_source)
        counts[bucket] = counts.get(bucket, 0) + int(count or 0)
    return counts


def _source_ingested_raw_ids(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
) -> dict[str, set[str]]:
    ids: dict[str, set[str]] = {}
    q = (
        select(
            CreatorSource.source_type,
            CreatorSource.platform,
            Creator.source,
            CreatorSource.raw_observation_id,
        )
        .join(Creator, Creator.id == CreatorSource.creator_id)
        .where(CreatorSource.raw_observation_id.is_not(None), CreatorSource.raw_observation_id != "")
    )
    where_department = department_where(CreatorSource, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = _apply_actor_filter(q, CreatorSource, actor_filter)
    for source_type, platform, fallback_source, raw_id in db.execute(q).all():
        bucket = _source_bucket_from_creator_source(source_type, platform, fallback_source)
        ids.setdefault(bucket, set()).add(str(raw_id or "").strip())
    return ids


def _compute_source_stats(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
    days: int = 7,
) -> dict[str, Any]:
    days = max(1, min(int(days or 7), 90))
    sources = empty_source_stats(days)
    today = datetime.now().date()

    q = select(
        RawObservation.id,
        RawObservation.platform,
        RawObservation.source,
        RawObservation.created_at,
        RawObservation.collected_at,
    )
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = _apply_actor_filter(q, RawObservation, actor_filter)
    q = _exclude_source_video_seed_rows(q)

    today_raw_ids: dict[str, set[str]] = {key: set() for key in SOURCE_KEYS}
    for raw_id, platform, source, created_at, collected_at in db.execute(q).all():
        bucket = classify_source(platform, source)
        stat = sources.get(bucket) or sources[SRC_OTHER]
        stat["total"] += 1
        day = _as_date(collected_at) or _as_date(created_at)
        ts = _iso_or_text(collected_at or created_at)
        if ts and (not stat["last_collected_at"] or ts > stat["last_collected_at"]):
            stat["last_collected_at"] = ts
        if day == today:
            stat["today"] += 1
            today_raw_ids.setdefault(bucket, set()).add(str(raw_id or "").strip())
        if day is not None and day.isoformat() in stat["daily"]:
            stat["daily"][day.isoformat()] += 1

    funnel_q = select(
        func.coalesce(func.sum(case((RawObservation.lead_status == "shop_list_seen", 1), else_=0)), 0),
        func.coalesce(func.sum(case((RawObservation.lead_status == "shop_profile_collected", 1), else_=0)), 0),
    ).where(RawObservation.platform == "tiktok_shop")
    if where_department is not None:
        funnel_q = funnel_q.where(where_department)
    funnel_q = _apply_actor_filter(funnel_q, RawObservation, actor_filter)
    shop_list_seen, shop_profile_collected = db.execute(funnel_q).one()

    contacts = _source_contacts_from_creators(
        db,
        department_code=department_code,
        actor_filter=actor_filter,
    )
    ingested_counts = _source_ingested_raw_counts(
        db,
        department_code=department_code,
        actor_filter=actor_filter,
    )
    ingested_ids = _source_ingested_raw_ids(
        db,
        department_code=department_code,
        actor_filter=actor_filter,
    )

    shaped: dict[str, dict[str, Any]] = {}
    for key in SOURCE_KEYS:
        stat = sources[key]
        ingested_total = int(ingested_counts.get(key, 0))
        today_ingested = len(today_raw_ids.get(key, set()) & ingested_ids.get(key, set()))
        out = {
            "total": stat["total"],
            "today": stat["today"],
            "daily": [{"date": day, "count": count} for day, count in stat["daily"].items()],
            "queued_total": max(0, int(stat["today"] or 0) - today_ingested),
            "ingested_total": ingested_total,
            "last_collected_at": stat.get("last_collected_at"),
        }
        if key in contacts:
            out["contacts"] = contacts[key]
        shaped[key] = out

    shaped[SRC_SHOP]["funnel"] = {
        "shop_list_seen": int(shop_list_seen or 0),
        "shop_profile_collected": int(shop_profile_collected or 0),
    }
    return {
        "generated_at": datetime.now().isoformat(),
        "sources": shaped,
    }


def get_source_stats(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
    days: int = 7,
) -> dict[str, Any]:
    days = max(1, min(int(days or 7), 90))
    return stats_cache.get_or_compute(
        "collector_source_stats",
        (department_code or "__all__", actor_filter or "__all__", days),
        lambda: _compute_source_stats(
            db,
            department_code=department_code,
            actor_filter=actor_filter,
            days=days,
        ),
        ttl_seconds=STATS_CACHE_TTL_SECONDS,
    )


def refresh_source_stats(
    db: Session,
    *,
    department_code: str | None,
    actor_filter: str | None,
    days: int = 7,
) -> None:
    days = max(1, min(int(days or 7), 90))
    stats_cache.refresh(
        "collector_source_stats",
        (department_code or "__all__", actor_filter or "__all__", days),
        lambda: _compute_source_stats(
            db,
            department_code=department_code,
            actor_filter=actor_filter,
            days=days,
        ),
        ttl_seconds=STATS_CACHE_TTL_SECONDS * 2,
    )


def _iter_actor_raw_rows(db: Session, actor_ids: set[str], department_code: str | None):
    if not actor_ids:
        return []
    q = select(
        RawObservation.id,
        RawObservation.actor_user_id,
        RawObservation.platform,
        RawObservation.source,
        RawObservation.created_at,
        RawObservation.collected_at,
        RawObservation.lead_status,
    ).where(RawObservation.actor_user_id.in_(actor_ids))
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = _exclude_source_video_seed_rows(q)
    return db.execute(q).all()


def _compute_actor_collection_stats_map(
    db: Session,
    actor_ids: Iterable[str],
    *,
    department_code: str | None = None,
) -> dict[str, dict[str, Any]]:
    ids = {str(actor_id or "").strip() for actor_id in actor_ids if str(actor_id or "").strip()}
    out = {actor_id: empty_collection_stats() for actor_id in ids}
    if not ids:
        return out

    today = datetime.now().date()
    today_raw_ids: dict[tuple[str, str], set[str]] = {}
    for raw_id, actor_user_id, platform, source, created_at, collected_at, lead_status in _iter_actor_raw_rows(db, ids, department_code):
        actor_key = str(actor_user_id or "").strip()
        if actor_key not in out:
            continue
        day = _as_date(collected_at) or _as_date(created_at)
        bucket = classify_source(platform, source)
        stats = out[actor_key]
        source_stats = stats["sources"][bucket]
        stats["total"] += 1
        source_stats["total"] += 1
        if day == today:
            stats["today"] += 1
            source_stats["today"] += 1
            today_raw_ids.setdefault((actor_key, bucket), set()).add(str(raw_id or "").strip())
        if day is not None and day.isoformat() in source_stats["daily"]:
            source_stats["daily"][day.isoformat()] += 1
        ts = _iso_or_text(collected_at or created_at)
        if ts and (not stats["last_collected_at"] or ts > stats["last_collected_at"]):
            stats["last_collected_at"] = ts
        if ts and (not source_stats["last_collected_at"] or ts > source_stats["last_collected_at"]):
            source_stats["last_collected_at"] = ts
        if bucket == SRC_SHOP:
            stats["shop_total"] += 1
            if day == today:
                stats["shop_today"] += 1
            if lead_status == "shop_profile_collected":
                stats["shop_detail_total"] += 1

    q = select(
        CreatorSource.actor_user_id,
        CreatorSource.source_type,
        CreatorSource.raw_observation_id,
        Creator,
    ).join(
        Creator,
        Creator.id == CreatorSource.creator_id,
    ).where(CreatorSource.actor_user_id.in_(ids))
    where_department = department_where(CreatorSource, department_code)
    if where_department is not None:
        q = q.where(where_department)

    seen: set[tuple[str, str, str]] = set()
    seen_raw: set[tuple[str, str, str]] = set()
    today_ingested_by_source: dict[tuple[str, str], int] = {}
    for actor_user_id, source_type, raw_observation_id, creator in db.execute(q).all():
        actor_key = str(actor_user_id or "").strip()
        if actor_key not in out:
            continue
        bucket = _source_bucket_from_creator_source(source_type, creator.platform, creator.source)
        if bucket != SRC_SHOP:
            continue

        raw_key = str(raw_observation_id or "").strip()
        if raw_key:
            raw_dedupe = (actor_key, bucket, raw_key)
            if raw_dedupe not in seen_raw:
                seen_raw.add(raw_dedupe)
                out[actor_key]["ingested_total"] += 1
                out[actor_key]["sources"][bucket]["ingested_total"] += 1
                if raw_key in today_raw_ids.get((actor_key, bucket), set()):
                    today_ingested_by_source[(actor_key, bucket)] = today_ingested_by_source.get((actor_key, bucket), 0) + 1

        dedupe = (actor_key, bucket, creator.id)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        has_email = bool(str(creator.email or "").strip())
        has_links = _has_links(creator)
        has_gmv = _has_gmv(creator)
        if has_email:
            out[actor_key]["with_email"] += 1
        if has_links:
            out[actor_key]["with_links"] += 1
        if has_gmv:
            out[actor_key]["with_gmv"] += 1
        if _has_detail_capture(creator) and (has_email or has_links or has_gmv):
            out[actor_key]["valid_detail_total"] += 1

    for actor_key, stats in out.items():
        for bucket in SOURCE_KEYS:
            source_stats = stats["sources"][bucket]
            source_stats["queued_total"] = max(
                0,
                int(source_stats.get("today") or 0) - int(today_ingested_by_source.get((actor_key, bucket), 0)),
            )
        stats["queued_total"] = max(
            0,
            int(stats.get("shop_today") or 0) - int(today_ingested_by_source.get((actor_key, SRC_SHOP), 0)),
        )

    return out


def get_actor_collection_stats_map(
    db: Session,
    actor_ids: Iterable[str],
    *,
    department_code: str | None = None,
) -> dict[str, dict[str, Any]]:
    ids = tuple(sorted(str(actor_id or "").strip() for actor_id in actor_ids if str(actor_id or "").strip()))
    if not ids:
        return {}
    return stats_cache.get_or_compute(
        "collector_actor_stats",
        (department_code or "__all__", ids),
        lambda: _compute_actor_collection_stats_map(db, ids, department_code=department_code),
        ttl_seconds=STATS_CACHE_TTL_SECONDS,
    )


def refresh_actor_collection_stats_map(
    db: Session,
    actor_ids: Iterable[str],
    *,
    department_code: str | None = None,
) -> None:
    ids = tuple(sorted(str(actor_id or "").strip() for actor_id in actor_ids if str(actor_id or "").strip()))
    if not ids:
        return
    stats_cache.refresh(
        "collector_actor_stats",
        (department_code or "__all__", ids),
        lambda: _compute_actor_collection_stats_map(db, ids, department_code=department_code),
        ttl_seconds=STATS_CACHE_TTL_SECONDS * 2,
    )


def get_actor_collection_stats(
    db: Session,
    actor_user_id: str,
    *,
    department_code: str | None = None,
) -> dict[str, Any]:
    return get_actor_collection_stats_map(db, [actor_user_id], department_code=department_code).get(
        actor_user_id,
        empty_collection_stats(),
    )
