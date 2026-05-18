from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.raw_observation import RawObservation
from ..services.collector_service import ingest_observation
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, department_where
from ..utils.source_classify import (
    SOURCE_OTHER as SRC_OTHER,
    SOURCE_SHOP as SRC_SHOP,
    SOURCE_TABLE_IMPORT as SRC_TABLE_IMPORT,
    SOURCE_X9_LEADS as SRC_X9_LEADS,
    classify_source as _classify,
)


_LEAD_STATUS_RE = re.compile(r'"lead_status"\s*:\s*"([^"]+)"')


router = APIRouter(prefix="/api/local/collector", tags=["collector"])


def _iso_or_text(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


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


@router.get("/recent-observations")
def recent(request: Request, limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    q = select(RawObservation)
    where_department = department_where(RawObservation, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    rows = list(
        db.scalars(
            q.order_by(
                func.coalesce(RawObservation.created_at, RawObservation.collected_at).desc(),
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


def _extract_item(bucket: str, r: RawObservation, payload: dict) -> dict:
    creator = payload.get("creator") or {}
    item = {
        "id": r.id,
        "source": bucket,
        "platform": r.platform,
        "handle": creator.get("handle") or "",
        "display_name": creator.get("display_name"),
        "followers_raw": creator.get("followers_raw"),
        "search_keyword": r.search_keyword or payload.get("search_keyword"),
        "collected_at": _iso_or_text(r.collected_at),
        "created_at": _iso_or_text(r.created_at),
    }
    if bucket == SRC_SHOP:
        shop = payload.get("tiktok_shop") or {}
        li = shop.get("list_item") or {}
        item["shop"] = {
            "lead_status": payload.get("lead_status"),
            "gmv_raw": li.get("gmv_raw"),
            "gpm_raw": li.get("gpm_raw"),
            "avg_commission_rate_raw": li.get("avg_commission_rate_raw"),
            "category_text": li.get("category_text"),
            "invite_status": li.get("invite_status"),
            "save_status": li.get("save_status"),
            "shop_profile_url": creator.get("shop_profile_url") or shop.get("source_page_url"),
            "detail_captured": bool(shop.get("raw_dom_html") or shop.get("raw_capture")),
        }
    elif bucket == SRC_X9_LEADS:
        item["lead"] = {
            "email": creator.get("email"),
            "external_links": creator.get("external_links") or [],
            "source_video_url": (payload.get("source_video") or {}).get("video_url"),
            "current_status": creator.get("current_status"),
        }
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
    funnel. Counts come from light columns; the funnel reads only the 1.2KB
    head of raw_json so the 1.5MB detail blobs never enter memory."""
    where_department = department_where(RawObservation, current_department_code(request))
    light_q = select(
        RawObservation.platform, RawObservation.source,
        RawObservation.created_at, RawObservation.collected_at,
    )
    if where_department is not None:
        light_q = light_q.where(where_department)
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
        ts = created_at or collected_at
        d = ts.date() if hasattr(ts, "date") else None
        if d == today:
            a["today"] += 1
        if d is not None and d.isoformat() in a["daily"]:
            a["daily"][d.isoformat()] += 1

    funnel = {"shop_list_seen": 0, "shop_profile_collected": 0}
    shop_q = select(func.substr(RawObservation.raw_json, 1, 1200)).where(
        RawObservation.platform == "tiktok_shop"
    )
    if where_department is not None:
        shop_q = shop_q.where(where_department)
    for (head,) in db.execute(shop_q).all():
        m = _LEAD_STATUS_RE.search(head or "")
        if m and m.group(1) in funnel:
            funnel[m.group(1)] += 1

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
    where_department = department_where(RawObservation, current_department_code(request))
    ts = func.coalesce(RawObservation.created_at, RawObservation.collected_at)
    light_q = select(RawObservation.id, RawObservation.platform, RawObservation.source)
    if where_department is not None:
        light_q = light_q.where(where_department)
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
        for oid in page_ids:
            r = full.get(oid)
            if r is None:
                continue
            try:
                payload = json.loads(r.raw_json) if r.raw_json else {}
            except (ValueError, TypeError):
                payload = {}
            items.append(_extract_item(bucket_by_id[oid], r, payload))
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}
