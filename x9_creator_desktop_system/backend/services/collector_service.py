"""collector_service.py — turns raw extension observations into creator rows.

This is the bridge between the chrome extension and the backend. It does:
1. Persist the raw observation (audit trail).
2. Normalize creator fields.
3. Upsert a Creator row (dedup by platform + handle).
4. Immediately score / tag / recommend the updated creator.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.raw_observation import RawObservation
from ..utils.contact_methods import has_contact_method
from ..utils.current_status import normalize_current_status
from ..utils.id_utils import content_hash, creator_id_for, new_id
from ..utils.json_utils import dumps_json, parse_followers_count
from ..utils.source_classify import classify_source
from .departments import DEFAULT_DEPARTMENT, normalize_department_code


def ingest_observation(db: Session, payload: dict[str, Any], *, auto_process: bool = True) -> dict[str, Any]:
    """Persist + upsert. Returns a small dict describing what happened."""
    if not isinstance(payload, dict):
        raise ValueError("observation payload must be a dict")
    if payload.get("event_type") != "creator_observation":
        raise ValueError("event_type must be 'creator_observation'")

    creator_data = payload.get("creator") or {}
    handle = (creator_data.get("handle") or "").strip()
    if not handle:
        raise ValueError("creator.handle is required")

    platform = (payload.get("platform") or "tiktok").lower()
    department_code = normalize_department_code(payload.get("department_code"), default=DEFAULT_DEPARTMENT)
    collected_at = _parse_dt(payload.get("collected_at")) or datetime.now()
    raw_blob = dumps_json(payload)
    obs = RawObservation(
        id=new_id("obs"),
        platform=platform,
        department_code=department_code,
        source=payload.get("source") or "chrome_extension",
        worker_id=payload.get("worker_id"),
        account_id=payload.get("account_id"),
        search_keyword=payload.get("search_keyword"),
        raw_json=raw_blob,
        content_hash=content_hash(raw_blob),
        collected_at=collected_at,
    )
    db.add(obs)
    # Persist the immutable audit row BEFORE the contact gate. TikTok Shop
    # list/detail observations carry no email/contact and would otherwise be
    # dropped here with no trace, making the primary source unobservable.
    db.commit()

    is_shop = platform == "tiktok_shop" or bool(payload.get("tiktok_shop"))
    if not is_shop and not _has_ingestable_contact(creator_data):
        # The legacy tiktok lead flow only keeps leads we can contact. TikTok
        # Shop creators are valid leads even with no email at collection time
        # (they're contacted via the affiliate-platform invite), so Shop
        # observations bypass this gate and always upsert a Creator.
        return {
            "ok": True,
            "creator_id": None,
            "handle": handle,
            "action": "skipped",
            "reason": "missing_contact",
            "observation_id": obs.id,
        }

    cid = creator_id_for(platform, handle)
    creator = db.get(Creator, cid)
    new = False
    if creator is None:
        creator = Creator(id=cid, platform=platform, handle=handle, department_code=department_code)
        db.add(creator)
        new = True
    creator.department_code = department_code or creator.department_code

    _merge_fields(creator, creator_data, payload)
    creator.last_seen_at = datetime.now(timezone.utc)

    db.commit()
    result = {
        "ok": True,
        "creator_id": creator.id,
        "handle": handle,
        "action": "inserted" if new else "updated",
        "observation_id": obs.id,
    }
    if auto_process:
        result["pipeline"] = _auto_process_creator(db, cid)
    return result


def _auto_process_creator(db: Session, creator_id: str) -> dict[str, Any]:
    from .pipeline import run_for_creator

    creator = db.get(Creator, creator_id)
    if creator is None:
        return {"ok": False, "error": "creator_not_found"}
    try:
        out = run_for_creator(db, creator)
        db.commit()
        return {"ok": True, **out}
    except Exception as exc:
        db.rollback()
        return {"ok": False, "error": str(exc)}


def _merge_fields(creator: Creator, c: dict, payload: dict) -> None:
    if c.get("display_name"):
        creator.display_name = c["display_name"]
    handle = (c.get("handle") or "").strip()
    if handle:
        # Always derive the canonical profile_url from the handle, NOT
        # from any URL the extension may have collected from a username.
        creator.profile_url = f"https://www.tiktok.com/@{handle}"
    if c.get("bio"):
        creator.bio = c["bio"]
    if c.get("followers_raw"):
        creator.followers_raw = c["followers_raw"]
        parsed = parse_followers_count(c["followers_raw"])
        if parsed is not None:
            creator.followers_count = parsed
    if isinstance(c.get("followers_count"), int):
        creator.followers_count = c["followers_count"]

    current_status = normalize_current_status(c.get("current_status") or payload.get("current_status"))
    if current_status:
        creator.current_status = current_status

    store_assigned = (c.get("store_assigned") or payload.get("store_assigned") or "").strip()
    if store_assigned:
        creator.store_assigned = store_assigned

    owner_bd = (c.get("owner_bd") or c.get("bd_owner") or payload.get("owner_bd") or payload.get("bd_owner") or "").strip()
    if owner_bd:
        creator.owner_bd = owner_bd

    email = (c.get("email") or "").strip().lower() or None
    if email:
        creator.email = email
        creator.has_email = 1
    elif creator.has_email is None:
        creator.has_email = 0

    if c.get("external_links") is not None:
        creator.external_links_json = dumps_json(c["external_links"])

    sv = payload.get("source_video") or {}
    sv_url = (sv.get("video_url") or "").strip()
    sv_title = sv.get("title")
    sv_desc = sv.get("description")

    # If source_video_url is actually a profile URL, do not treat it as
    # a video — null out the video fields so scoring won't be tricked.
    if sv_url and "/video/" not in sv_url:
        creator.source_video_url = None  # not a real video URL
    elif sv_url:
        creator.source_video_url = sv_url
    if sv_title:
        creator.source_video_title = sv_title
    if sv_desc:
        creator.source_video_description = sv_desc

    sk = payload.get("search_keyword")
    if sk:
        creator.search_keyword = sk

    # This is the plugin's latest collection time for the creator.
    creator.collected_at = _parse_dt(payload.get("collected_at")) or datetime.now()

    # Which of the 3 acquisition channels this creator came from. Use the same
    # default the RawObservation row stores ("chrome_extension") so the ingest
    # and read sides classify identically.
    creator.source = classify_source(
        (payload.get("platform") or "tiktok").lower(),
        payload.get("source") or "chrome_extension",
    )

    if payload.get("tiktok_shop"):
        _merge_tiktok_shop(creator, payload)


def _merge_tiktok_shop(creator: Creator, payload: dict) -> None:
    """Promote TikTok Shop list/detail fields onto the Creator. The huge
    raw_dom_html / raw_visible_text are deliberately NOT copied here — they
    stay only in raw_observations.raw_json. List and detail observations for
    the same handle are merged so neither phase blanks the other's fields."""
    shop = payload.get("tiktok_shop") or {}
    li = shop.get("list_item") or {}
    c = payload.get("creator") or {}

    avatar = c.get("avatar_url") or li.get("avatar_url")
    if avatar:
        creator.avatar_url = avatar
    shop_url = c.get("shop_profile_url") or shop.get("source_page_url")
    if shop_url:
        creator.shop_profile_url = shop_url
    if payload.get("lead_status"):
        creator.lead_status = payload["lead_status"]

    metrics: dict[str, Any] = {}
    if creator.tiktok_shop_json:
        try:
            metrics = json.loads(creator.tiktok_shop_json) or {}
        except (ValueError, TypeError):
            metrics = {}

    for key in (
        "gmv_raw", "gpm_raw", "avg_commission_rate_raw",
        "category_text", "invite_status", "save_status", "row_index",
    ):
        val = li.get(key)
        if val is not None and val != "":
            metrics[key] = val
    src_page = li.get("source_page_url") or shop.get("source_page_url")
    if src_page:
        metrics["source_page_url"] = src_page

    raw_capture = shop.get("raw_capture") or {}
    if shop.get("raw_dom_html") or raw_capture:
        links = raw_capture.get("links")
        metrics["detail_captured"] = True
        metrics["detail_links_count"] = len(links) if isinstance(links, list) else 0
        if raw_capture.get("captured_at"):
            metrics["detail_captured_at"] = raw_capture["captured_at"]
    metrics.setdefault("detail_captured", False)
    creator.tiktok_shop_json = dumps_json(metrics)


def _has_ingestable_contact(c: dict[str, Any]) -> bool:
    email = (c.get("email") or "").strip()
    if not email and isinstance(c.get("emails"), list):
        email = next((str(v).strip() for v in c["emails"] if str(v).strip()), "")
    return has_contact_method(email, c.get("bio"), c.get("external_links"))


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return None
