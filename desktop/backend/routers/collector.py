from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.creator import Creator
from ..models.raw_observation import RawObservation
from ..services.collector_service import ingest_observation, reprocess_raw_observations
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, department_where
from ..services.observation_enrichment import enrich_observation_payload, extract_shop_detail_fields
from ..utils.contact_methods import extract_contact_methods
from ..utils.json_utils import loads_json_list
from ..utils.source_classify import (
    SOURCE_OTHER as SRC_OTHER,
    SOURCE_SHOP as SRC_SHOP,
    SOURCE_TABLE_IMPORT as SRC_TABLE_IMPORT,
    SOURCE_X9_LEADS as SRC_X9_LEADS,
    classify_source as _classify,
)

router = APIRouter(prefix="/api/local/collector", tags=["collector"])
SOURCE_VIDEO_SEED_PATTERN = '%"lead_status":"source_video_seen"%'


def _iso_or_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _observation_timestamp(created_at: Any, collected_at: Any) -> Any:
    return collected_at or created_at


def _observation_day(created_at: Any, collected_at: Any):
    ts = _observation_timestamp(created_at, collected_at)
    if hasattr(ts, "date"):
        return ts.date()
    text = str(ts or "").strip()
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


@router.post("/observations")
def post_observation(payload: dict[str, Any], request: Request, db: Session = Depends(get_db)) -> dict:
    try:
        if getattr(request.state, "current_user", None):
            payload.setdefault("department_code", current_department_code(request))
        else:
            payload.setdefault("department_code", DEFAULT_DEPARTMENT)
        return ingest_observation(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/reprocess-raw")
def reprocess_raw(
    request: Request,
    body: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
) -> dict:
    body = body or {}
    return reprocess_raw_observations(
        db,
        limit=body.get("limit", 1000),
        platform=body.get("platform", "tiktok_shop"),
        department_code=current_department_code(request),
        skip_invalid_handle_repairs=body.get("skip_invalid_handle_repairs", True) is not False,
        auto_process=body.get("auto_process", True) is not False,
    )


@router.get("/recent-observations")
def recent(request: Request, limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    q = select(RawObservation)
    department_code = current_department_code(request)
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        q = q.where(where_department)
    rows = list(
        db.scalars(
            q.order_by(
                func.coalesce(RawObservation.collected_at, RawObservation.created_at).desc(),
                RawObservation.id.desc(),
            ).limit(limit)
        ).all()
    )
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "platform": r.platform,
            "worker_id": r.worker_id,
            "account_id": r.account_id,
            "search_keyword": r.search_keyword,
            "content_hash": r.content_hash,
            "collected_at": _iso_or_text(r.collected_at),
            "created_at": _iso_or_text(r.created_at),
        })
    return {"ok": True, "items": out}


def _date_bounds(date_from: str | None, date_to: str | None):
    start = end = None
    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            start = None
    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            end = None
    return start, end


def _exclude_source_video_seed_rows(q):
    return q.where(or_(RawObservation.raw_json.is_(None), ~RawObservation.raw_json.like(SOURCE_VIDEO_SEED_PATTERN)))


def _handle_lookup_key(value: Any) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _creator_feed_lookup(db: Session, department_code: str | None, handle_keys: set[str]) -> dict[str, dict[str, Any]]:
    keys = {key for key in handle_keys if key}
    if not keys:
        return {}
    lookup_values = sorted(keys | {f"@{key}" for key in keys})
    q = select(Creator).where(func.lower(func.trim(Creator.handle)).in_(lookup_values))
    where_department = department_where(Creator, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = q.order_by(func.coalesce(Creator.updated_at, Creator.last_seen_at, Creator.collected_at).desc())
    out: dict[str, dict[str, Any]] = {}
    for c in db.scalars(q).all():
        key = _handle_lookup_key(c.handle)
        if not key or key in out:
            continue
        out[key] = {
            "display_name": c.display_name,
            "followers_raw": c.followers_raw,
            "email": c.email,
            "external_links": loads_json_list(c.external_links_json),
            "bio": c.bio,
            "current_status": c.current_status,
            "source_video_url": c.source_video_url,
        }
    return out


def _lead_block(
    creator: dict[str, Any],
    payload: dict[str, Any],
    fallback: dict[str, Any] | None,
    *,
    source_video_url: str | None,
) -> dict[str, Any]:
    fallback = fallback or {}
    email = creator.get("email") or fallback.get("email")
    links = creator.get("external_links") or fallback.get("external_links") or []
    bio = creator.get("bio") or fallback.get("bio")
    methods = extract_contact_methods(email, bio, links)
    status = (
        creator.get("current_status")
        or payload.get("current_status")
        or payload.get("lead_status")
        or fallback.get("current_status")
    )
    if not status and not methods and not links:
        status = "raw_only_no_contact"
    return {
        "email": email,
        "external_links": links,
        "contact_methods": methods,
        "contact_types": list(dict.fromkeys(m["type"] for m in methods)),
        "source_video_url": source_video_url or fallback.get("source_video_url"),
        "current_status": status,
    }


def _extract_item(
    bucket: str,
    r: RawObservation,
    payload: dict,
    creator_fallback: dict[str, Any] | None = None,
    *,
    already_enriched: bool = False,
) -> dict:
    if bucket in {SRC_SHOP, SRC_X9_LEADS} and not already_enriched:
        payload = enrich_observation_payload(payload)
    creator = payload.get("creator") or {}
    fallback = creator_fallback or {}
    item = {
        "id": r.id,
        "source": bucket,
        "platform": r.platform,
        "handle": creator.get("handle") or "",
        "display_name": creator.get("display_name") or fallback.get("display_name"),
        "followers_raw": creator.get("followers_raw") or fallback.get("followers_raw"),
        "search_keyword": r.search_keyword or payload.get("search_keyword"),
        "collected_at": _iso_or_text(r.collected_at),
        "created_at": _iso_or_text(r.created_at),
    }
    if bucket == SRC_SHOP:
        shop = payload.get("tiktok_shop") or {}
        li = shop.get("list_item") or {}
        server_fields = shop.get("server_extracted") if isinstance(shop.get("server_extracted"), dict) else {}
        if not server_fields:
            server_fields = extract_shop_detail_fields(str(shop.get("raw_visible_text") or ""))
        item["shop"] = {
            "lead_status": payload.get("lead_status"),
            "gmv_raw": li.get("gmv_raw") or server_fields.get("gmv_raw"),
            "gpm_raw": li.get("gpm_raw") or server_fields.get("gpm_raw"),
            "avg_commission_rate_raw": li.get("avg_commission_rate_raw") or server_fields.get("avg_commission_rate_raw"),
            "category_text": li.get("category_text") or server_fields.get("category_text"),
            "invite_status": li.get("invite_status"),
            "save_status": li.get("save_status"),
            "shop_profile_url": creator.get("shop_profile_url") or shop.get("source_page_url"),
            "detail_captured": bool(shop.get("raw_dom_html") or shop.get("raw_capture")),
        }
        item["followers_raw"] = creator.get("followers_raw") or server_fields.get("followers_raw") or fallback.get("followers_raw")
        item["lead"] = _lead_block(creator, payload, fallback, source_video_url=None)
    elif bucket == SRC_X9_LEADS:
        item["lead"] = _lead_block(
            creator,
            payload,
            fallback,
            source_video_url=(payload.get("source_video") or {}).get("video_url"),
        )
    elif bucket == SRC_TABLE_IMPORT:
        meta = payload.get("import_meta") or {}
        item["import_meta"] = {
            "country": meta.get("country"),
            "tier": meta.get("tier"),
            "language": meta.get("language"),
            "engagement_rate": meta.get("engagement_rate"),
            "quality_score": meta.get("quality_score"),
            "email": creator.get("email"),
        }
    return item


@router.get("/source-stats")
def source_stats(request: Request, db: Session = Depends(get_db)) -> dict:
    """Per-source totals / today / 7-day series + the TikTok Shop list->detail
    funnel. Counts stay database-side so large detail blobs are not loaded into
    Python just to build dashboard counters."""
    department_code = current_department_code(request)
    where_department = department_where(RawObservation, department_code)
    light_q = select(
        RawObservation.platform, RawObservation.source,
        RawObservation.created_at, RawObservation.collected_at,
    )
    if where_department is not None:
        light_q = light_q.where(where_department)
    light_q = _exclude_source_video_seed_rows(light_q)
    rows = db.execute(light_q).all()

    today = datetime.now().date()
    day_keys = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]

    def blank() -> dict:
        return {"total": 0, "today": 0, "daily": {k: 0 for k in day_keys}}

    agg = {
        SRC_SHOP: blank(), SRC_X9_LEADS: blank(),
        SRC_TABLE_IMPORT: blank(), SRC_OTHER: blank(),
    }
    for platform, source, created_at, collected_at in rows:
        a = agg[_classify(platform, source)]
        a["total"] += 1
        d = _observation_day(created_at, collected_at)
        if d == today:
            a["today"] += 1
        if d is not None and d.isoformat() in a["daily"]:
            a["daily"][d.isoformat()] += 1

    funnel_q = select(
        func.coalesce(func.sum(case((RawObservation.raw_json.like('%"lead_status":"shop_list_seen"%'), 1), else_=0)), 0),
        func.coalesce(func.sum(case((RawObservation.raw_json.like('%"lead_status":"shop_profile_collected"%'), 1), else_=0)), 0),
    ).where(RawObservation.platform == "tiktok_shop")
    if where_department is not None:
        funnel_q = funnel_q.where(where_department)
    shop_list_seen, shop_profile_collected = db.execute(funnel_q).one()
    funnel = {
        "shop_list_seen": int(shop_list_seen or 0),
        "shop_profile_collected": int(shop_profile_collected or 0),
    }

    def shaped(bucket: str) -> dict:
        a = agg[bucket]
        return {
            "total": a["total"],
            "today": a["today"],
            "daily": [{"date": k, "count": a["daily"][k]} for k in day_keys],
        }

    shop = shaped(SRC_SHOP)
    shop["funnel"] = funnel
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "sources": {
            SRC_SHOP: shop,
            SRC_X9_LEADS: shaped(SRC_X9_LEADS),
            SRC_TABLE_IMPORT: shaped(SRC_TABLE_IMPORT),
            SRC_OTHER: shaped(SRC_OTHER),
        },
    }


@router.get("/observations-feed")
def observations_feed(
    request: Request,
    source: str = Query(default="all"),
    platform: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Paginated, source-filtered observation feed. Classifies on light columns
    over the full scan, then loads raw_json only for the requested page."""
    department_code = current_department_code(request)
    where_department = department_where(RawObservation, department_code)
    ts = func.coalesce(RawObservation.collected_at, RawObservation.created_at)
    light_q = select(RawObservation.id, RawObservation.platform, RawObservation.source)
    if where_department is not None:
        light_q = light_q.where(where_department)
    light_q = _exclude_source_video_seed_rows(light_q)
    start, end = _date_bounds(date_from, date_to)
    if start is not None:
        light_q = light_q.where(ts >= start)
    if end is not None:
        light_q = light_q.where(ts <= end)
    light_q = light_q.order_by(ts.desc(), RawObservation.id.desc())

    want = (source or "all").lower().strip()
    plat = platform.lower() if platform else None
    ordered_ids: list[str] = []
    bucket_by_id: dict[str, str] = {}
    for oid, p, s in db.execute(light_q).all():
        bucket = _classify(p, s)
        if want not in ("all", "", bucket):
            continue
        if plat and (p or "").lower() != plat:
            continue
        ordered_ids.append(oid)
        bucket_by_id[oid] = bucket

    total = len(ordered_ids)
    page_ids = ordered_ids[offset:offset + limit]
    items: list[dict] = []
    if page_ids:
        full = {
            r.id: r
            for r in db.scalars(
                select(RawObservation).where(RawObservation.id.in_(page_ids))
            ).all()
        }
        prepared: list[tuple[str, RawObservation, dict, str]] = []
        handle_keys: set[str] = set()
        for oid in page_ids:
            r = full.get(oid)
            if r is None:
                continue
            try:
                payload = json.loads(r.raw_json) if r.raw_json else {}
            except (ValueError, TypeError):
                payload = {}
            bucket = bucket_by_id[oid]
            if bucket in {SRC_SHOP, SRC_X9_LEADS}:
                payload = enrich_observation_payload(payload)
            creator = payload.get("creator") if isinstance(payload.get("creator"), dict) else {}
            handle_key = _handle_lookup_key(creator.get("handle"))
            if handle_key:
                handle_keys.add(handle_key)
            prepared.append((bucket, r, payload, handle_key))
        fallback_by_handle = _creator_feed_lookup(db, department_code, handle_keys)
        for bucket, r, payload, handle_key in prepared:
            items.append(
                _extract_item(
                    bucket,
                    r,
                    payload,
                    fallback_by_handle.get(handle_key),
                    already_enriched=bucket in {SRC_SHOP, SRC_X9_LEADS},
                )
            )
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}
