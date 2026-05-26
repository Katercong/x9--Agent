from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.app_user import AppUser
from ..models.creator import Creator
from ..models.creator_source import CreatorSource
from ..models.extension_run_progress import ExtensionRunProgress
from ..models.extension_session import ExtensionSession
from ..models.raw_observation import RawObservation
from ..services.collector_service import queue_observation, reprocess_raw_observations
from ..services.collection_stats_service import (
    SHOP_QUEUE_CLEARED_STATUS,
    get_actor_collection_stats_map,
    get_source_stats as get_db_source_stats,
)
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
UNASSIGNED_ACTOR = "__unassigned__"
ADMIN_ROLES = {"super_admin", "company_admin", "department_admin"}


def _actor_id(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    return str(user.get("id") or user.get("identity") or "").strip() or None


def _is_admin_user(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("entry_scope") == "admin" and user.get("role") in ADMIN_ROLES)


def _is_admin_role(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("role") in ADMIN_ROLES)


def _collection_actor_id(user: dict[str, Any] | None) -> str | None:
    if not user or _is_admin_role(user):
        return None
    return _actor_id(user)


def _actor_payload(user: dict[str, Any] | None = None, row: AppUser | None = None) -> dict[str, Any] | None:
    if user:
        actor_id = _actor_id(user)
        if not actor_id:
            return None
        return {
            "id": actor_id,
            "username": user.get("username"),
            "display_name": user.get("display_name"),
            "email": user.get("email"),
            "role": user.get("role"),
            "department_code": user.get("department_code"),
        }
    if row is None:
        return None
    return {
        "id": row.id,
        "username": row.username,
        "display_name": row.display_name,
        "email": row.email,
        "role": row.role,
        "department_code": row.department_code,
    }


def _payload_actor_id(payload: dict[str, Any]) -> str | None:
    actor_id = str(payload.get("actor_user_id") or "").strip()
    if actor_id:
        return actor_id
    actor = payload.get("actor")
    if isinstance(actor, dict):
        actor_id = str(actor.get("id") or actor.get("identity") or "").strip()
        if actor_id:
            return actor_id
    return None


def _apply_worker_binding_attribution(db: Session, payload: dict[str, Any], request: Request) -> None:
    user = getattr(request.state, "current_user", None)
    worker_id = str(payload.get("worker_id") or "").strip()
    session_actor_id = _collection_actor_id(user)
    payload_actor_id = _payload_actor_id(payload)
    actor_user_id = session_actor_id or payload_actor_id
    actor_row: AppUser | None = None

    if user:
        payload["department_code"] = current_department_code(request) or user.get("department_code") or DEFAULT_DEPARTMENT
        if session_actor_id:
            actor_user_id = session_actor_id
            payload["actor_user_id"] = session_actor_id
            payload["actor"] = _actor_payload(user=user)

    if worker_id:
        sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
        if sess is not None:
            if session_actor_id:
                sess.actor_user_id = session_actor_id
            elif payload_actor_id:
                sess.actor_user_id = payload_actor_id
            if not actor_user_id and sess.actor_user_id:
                actor_user_id = sess.actor_user_id
            if not payload.get("department_code") and sess.department_code:
                payload["department_code"] = sess.department_code

    if actor_user_id and not session_actor_id:
        actor_row = db.get(AppUser, actor_user_id)
        if actor_row is not None and int(actor_row.is_active or 0) == 1 and actor_row.role not in ADMIN_ROLES:
            payload["actor_user_id"] = actor_row.id
            payload["actor"] = _actor_payload(row=actor_row)
            if actor_row.department_code:
                payload["department_code"] = actor_row.department_code
        else:
            payload.pop("actor_user_id", None)
            payload.pop("actor", None)

    payload.setdefault("department_code", DEFAULT_DEPARTMENT)


def _require_bound_shop_actor(payload: dict[str, Any]) -> None:
    platform = str(payload.get("platform") or "").strip().lower()
    if platform != "tiktok_shop":
        return
    if _payload_actor_id(payload):
        return
    raise HTTPException(status_code=409, detail="actor_binding_required")


def _requested_actor_filter(request: Request, actor_user_id: str | None = None) -> str | None:
    user = getattr(request.state, "current_user", None)
    current_actor = _actor_id(user)
    if not _is_admin_user(user):
        if not current_actor:
            raise HTTPException(status_code=401, detail="login required")
        return current_actor
    requested = str(actor_user_id or "").strip()
    if requested in {"", "all", "*"}:
        return None
    if requested in {"unassigned", UNASSIGNED_ACTOR}:
        return UNASSIGNED_ACTOR
    return requested


def _apply_actor_filter(q, model, actor_filter: str | None):
    if actor_filter is None:
        return q
    column = getattr(model, "actor_user_id")
    if actor_filter == UNASSIGNED_ACTOR:
        return q.where(or_(column.is_(None), column == ""))
    return q.where(column == actor_filter)


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


def _json_obj(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _coerce_observation_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "ignore")
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid observation JSON")
        if isinstance(parsed, dict):
            return parsed
    raise HTTPException(status_code=400, detail="observation payload must be a JSON object")


@router.options("/observations")
def observations_options() -> Response:
    return Response(status_code=204)


@router.post("/observations")
def post_observation(request: Request, payload: Any = Body(...), db: Session = Depends(get_db)) -> dict:
    try:
        payload = _coerce_observation_payload(payload)
        _apply_worker_binding_attribution(db, payload, request)
        _require_bound_shop_actor(payload)
        return queue_observation(db, payload)
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
        queued_only=body.get("queued_only", False) is True,
    )


@router.get("/recent-observations")
def recent(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    actor_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    q = select(RawObservation)
    department_code = current_department_code(request)
    actor_filter = _requested_actor_filter(request, actor_user_id)
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = _apply_actor_filter(q, RawObservation, actor_filter)
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
            "actor_user_id": r.actor_user_id,
            "worker_id": r.worker_id,
            "account_id": r.account_id,
            "search_keyword": r.search_keyword,
            "content_hash": r.content_hash,
            "collected_at": _iso_or_text(r.collected_at),
            "created_at": _iso_or_text(r.created_at),
        })
    return {"ok": True, "items": out}


@router.get("/actors")
def collection_actors(request: Request, db: Session = Depends(get_db)) -> dict:
    user = getattr(request.state, "current_user", None)
    current_actor = _actor_id(user)
    admin_view = _is_admin_user(user)
    if not current_actor and not admin_view:
        raise HTTPException(status_code=401, detail="login required")

    department_code = current_department_code(request)
    users_q = (
        select(AppUser)
        .where(AppUser.role == "department_user", AppUser.is_active == 1)
        .order_by(AppUser.username.asc())
    )
    if department_code is not None:
        users_q = users_q.where(AppUser.department_code == department_code)
    if not admin_view:
        users_q = users_q.where(AppUser.id == current_actor)
    users = list(db.scalars(users_q).all())
    stats_by_actor = get_actor_collection_stats_map(
        db,
        [row.id for row in users],
        department_code=department_code,
    )
    user_status_by_actor = _shop_user_status_map(db, request, [row.id for row in users])
    unassigned_sources = get_db_source_stats(
        db,
        department_code=department_code,
        actor_filter=UNASSIGNED_ACTOR,
    )["sources"]
    unassigned = {
        "total": sum(int(bucket.get("total") or 0) for bucket in unassigned_sources.values()),
        "today": sum(int(bucket.get("today") or 0) for bucket in unassigned_sources.values()),
        "sources": unassigned_sources,
        "recent_workers": [],
    }
    ts = func.coalesce(RawObservation.collected_at, RawObservation.created_at)
    worker_q = (
        select(
            RawObservation.worker_id,
            RawObservation.platform,
            RawObservation.source,
            func.count(RawObservation.id),
            func.max(ts),
        )
        .where(or_(RawObservation.actor_user_id.is_(None), RawObservation.actor_user_id == ""))
        .group_by(RawObservation.worker_id, RawObservation.platform, RawObservation.source)
        .order_by(func.max(ts).desc())
        .limit(5)
    )
    where_department = department_where(RawObservation, department_code)
    if where_department is not None:
        worker_q = worker_q.where(where_department)
    worker_q = _exclude_source_video_seed_rows(worker_q)
    unassigned["recent_workers"] = [
        {
            "worker_id": worker_id,
            "platform": platform,
            "source": source,
            "total": int(total or 0),
            "last_collected_at": _iso_or_text(last_at),
        }
        for worker_id, platform, source, total, last_at in db.execute(worker_q).all()
    ]
    items = []
    for row in users:
        stat = stats_by_actor.get(row.id, {"total": 0, "today": 0})
        stat["user_status"] = user_status_by_actor.get(row.id, stat.get("user_status") or "offline")
        items.append({
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name,
            "email": row.email,
            "role": row.role,
            "department_code": row.department_code,
            "collection": stat,
        })
    return {
        "ok": True,
        "items": items,
        "unassigned": unassigned,
        "scope": "admin" if admin_view else "user",
    }


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
    return q.where(
        or_(
            RawObservation.lead_status.is_(None),
            ~RawObservation.lead_status.in_(["source_video_seen", SHOP_QUEUE_CLEARED_STATUS]),
        )
    )


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
        "actor_user_id": r.actor_user_id,
        "worker_id": r.worker_id,
        "account_id": r.account_id,
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
def source_stats(
    request: Request,
    actor_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Per-source totals / today / 7-day series + the TikTok Shop list->detail
    funnel. Counts stay database-side so large detail blobs are not loaded into
    Python just to build dashboard counters."""
    department_code = current_department_code(request)
    actor_filter = _requested_actor_filter(request, actor_user_id)
    stats = get_db_source_stats(
        db,
        department_code=department_code,
        actor_filter=actor_filter,
    )
    return {
        "ok": True,
        "generated_at": stats["generated_at"],
        "sources": stats["sources"],
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
    actor_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Paginated, source-filtered observation feed. Classifies on light columns
    over the full scan, then loads raw_json only for the requested page."""
    department_code = current_department_code(request)
    actor_filter = _requested_actor_filter(request, actor_user_id)
    where_department = department_where(RawObservation, department_code)
    ts = func.coalesce(RawObservation.collected_at, RawObservation.created_at)
    want = (source or "all").lower().strip()
    plat = platform.lower() if platform else None
    light_q = select(RawObservation.id, RawObservation.platform, RawObservation.source)
    if where_department is not None:
        light_q = light_q.where(where_department)
    light_q = _apply_actor_filter(light_q, RawObservation, actor_filter)
    light_q = _exclude_source_video_seed_rows(light_q)
    if plat:
        light_q = light_q.where(func.lower(RawObservation.platform) == plat)
    start, end = _date_bounds(date_from, date_to)
    if start is not None:
        light_q = light_q.where(ts >= start)
    if end is not None:
        light_q = light_q.where(ts <= end)
    light_q = light_q.order_by(ts.desc(), RawObservation.id.desc())

    ordered_ids: list[str] = []
    bucket_by_id: dict[str, str] = {}
    can_page_in_db = want in ("all", "") or (want == SRC_SHOP and plat == "tiktok_shop")
    if can_page_in_db:
        total = int(db.scalar(select(func.count()).select_from(light_q.order_by(None).subquery())) or 0)
        for oid, p, s in db.execute(light_q.limit(limit).offset(offset)).all():
            ordered_ids.append(oid)
            bucket_by_id[oid] = _classify(p, s)
        page_ids = ordered_ids
    else:
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
        ingested_by_raw_id = {
            raw_id: _iso_or_text(updated_at)
            for raw_id, updated_at in db.execute(
                select(CreatorSource.raw_observation_id, func.max(CreatorSource.updated_at))
                .where(CreatorSource.raw_observation_id.in_(page_ids))
                .group_by(CreatorSource.raw_observation_id)
            ).all()
            if raw_id
        }
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
            item = _extract_item(
                bucket,
                r,
                payload,
                fallback_by_handle.get(handle_key),
                already_enriched=bucket in {SRC_SHOP, SRC_X9_LEADS},
            )
            item["ingest_status"] = "ingested" if r.id in ingested_by_raw_id else "queued"
            item["ingested_at"] = ingested_by_raw_id.get(r.id)
            items.append(item)
    return {"ok": True, "total": total, "limit": limit, "offset": offset, "items": items}


def _as_aware_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not hasattr(value, "tzinfo"):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_shop_worker(session: ExtensionSession, progress: ExtensionRunProgress | None) -> bool:
    settings_obj = _json_obj(progress.settings_json if progress else None)
    text = " ".join(
        str(value or "")
        for value in (
            settings_obj.get("source"),
            settings_obj.get("extension_id"),
            settings_obj.get("account_id"),
            session.extension_id,
            session.worker_id,
            session.account_id,
        )
    ).lower()
    return "tiktok_shop" in text or str(session.worker_id or "").lower().startswith("tiktok_shop_")


def _shop_user_status_map(db: Session, request: Request, actor_ids: list[str]) -> dict[str, str]:
    ids = {str(actor_id or "").strip() for actor_id in actor_ids if str(actor_id or "").strip()}
    if not ids:
        return {}
    threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.extension_offline_seconds)
    department_code = current_department_code(request)
    q = select(ExtensionSession).where(ExtensionSession.actor_user_id.in_(ids))
    where_department = department_where(ExtensionSession, department_code)
    if where_department is not None:
        q = q.where(where_department)
    sessions = list(db.scalars(q).all())
    worker_ids = {s.worker_id for s in sessions if s.worker_id}
    progress_by_worker = {
        row.worker_id: row
        for row in db.scalars(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id.in_(worker_ids))).all()
    } if worker_ids else {}
    statuses = {actor_id: "offline" for actor_id in ids}
    for session in sessions:
        actor_id = str(session.actor_user_id or "").strip()
        if actor_id not in statuses:
            continue
        progress = progress_by_worker.get(session.worker_id)
        if not _is_shop_worker(session, progress):
            continue
        last = _as_aware_utc(session.last_heartbeat_at)
        online = bool(last and last >= threshold)
        if online:
            statuses[actor_id] = "online"
    return statuses


def _shop_worker_sessions(db: Session, request: Request, actor_filter: str | None) -> list[dict[str, Any]]:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.extension_offline_seconds)
    department_code = current_department_code(request)
    q = select(ExtensionSession)
    where_department = department_where(ExtensionSession, department_code)
    if where_department is not None:
        q = q.where(where_department)
    if actor_filter is not None:
        q = q.where(or_(
            ExtensionSession.actor_user_id == actor_filter,
            ExtensionSession.actor_user_id.is_(None),
            ExtensionSession.actor_user_id == "",
        ))
    sessions = list(db.scalars(q.order_by(ExtensionSession.last_heartbeat_at.desc())).all())
    worker_ids = {s.worker_id for s in sessions if s.worker_id}
    progress_by_worker = {
        row.worker_id: row
        for row in db.scalars(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id.in_(worker_ids))).all()
    } if worker_ids else {}
    actor_ids = {s.actor_user_id for s in sessions if s.actor_user_id}
    actors = {
        row.id: row
        for row in db.scalars(select(AppUser).where(AppUser.id.in_(actor_ids))).all()
    } if actor_ids else {}

    out: list[dict[str, Any]] = []
    seen_workers: set[str] = set()
    for s in sessions:
        if s.worker_id in seen_workers:
            continue
        progress = progress_by_worker.get(s.worker_id)
        if not _is_shop_worker(s, progress):
            continue
        seen_workers.add(s.worker_id)
        settings_obj = _json_obj(progress.settings_json if progress else None)
        last = _as_aware_utc(s.last_heartbeat_at)
        actor = actors.get(s.actor_user_id or "")
        out.append({
            "session_id": s.id,
            "department_code": s.department_code,
            "actor_user_id": s.actor_user_id,
            "actor": {
                "id": actor.id,
                "username": actor.username,
                "display_name": actor.display_name,
                "email": actor.email,
                "role": actor.role,
                "department_code": actor.department_code,
            } if actor else None,
            "worker_id": s.worker_id,
            "account_id": s.account_id,
            "extension_id": s.extension_id,
            "source": settings_obj.get("source"),
            "status": settings_obj.get("status") or (progress.step if progress else s.status),
            "session_status": s.status,
            "running": bool(progress.running) if progress else False,
            "current_action": progress.current_action if progress else None,
            "current_handle": progress.current_handle if progress else None,
            "search_keyword": progress.keyword if progress else None,
            "hourly_limit": settings_obj.get("hourly_limit"),
            "hourly_used": settings_obj.get("hourly_used"),
            "hourly_remaining": settings_obj.get("hourly_remaining"),
            "next_resume_at": settings_obj.get("next_resume_at"),
            "last_error": progress.last_error if progress else None,
            "extension_version": s.extension_version,
            "current_url": s.current_url,
            "page_type": s.page_type,
            "tiktok_page_status": s.tiktok_page_status,
            "tiktok_login_status": s.tiktok_login_status,
            "online": bool(last and last >= threshold),
            "last_heartbeat_at": last.isoformat() if last else None,
        })
    return out


@router.get("/shop-summary")
def shop_summary(
    request: Request,
    actor_user_id: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    actor_filter = _requested_actor_filter(request, actor_user_id)
    stats_payload = source_stats(request=request, actor_user_id=actor_user_id, db=db)
    feed_payload = observations_feed(
        request=request,
        source=SRC_SHOP,
        platform="tiktok_shop",
        date_from=None,
        date_to=None,
        limit=limit,
        offset=0,
        actor_user_id=actor_user_id,
        db=db,
    )
    user = getattr(request.state, "current_user", None)
    stats = dict((stats_payload.get("sources") or {}).get(SRC_SHOP, {}))
    if actor_filter and actor_filter != UNASSIGNED_ACTOR:
        status = _shop_user_status_map(db, request, [actor_filter]).get(actor_filter)
        if status:
            stats["user_status"] = status
    recent = dict(feed_payload)
    recent["items"] = [
        {
            key: value
            for key, value in item.items()
            if key not in {"worker_id", "account_id", "actor_user_id"}
        }
        for item in feed_payload.get("items", [])
        if isinstance(item, dict)
    ]
    return {
        "ok": True,
        "generated_at": datetime.now().isoformat(),
        "scope": {
            "actor_user_id": actor_filter,
            "admin": _is_admin_user(user),
            "department_code": current_department_code(request),
        },
        "stats": stats,
        "recent": recent,
    }
