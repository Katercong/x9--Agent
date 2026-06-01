"""collector_service.py — turns raw extension observations into creator rows.

This is the bridge between the chrome extension and the backend. It does:
1. Persist the raw observation (audit trail).
2. Normalize creator fields.
3. Upsert a Creator row (dedup by platform + handle).
4. Immediately score / tag / recommend the updated creator.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.raw_observation import RawObservation
from ..utils.contact_methods import has_contact_method
from ..utils.current_status import normalize_current_status
from ..utils.id_utils import content_hash, creator_id_for, new_id
from ..utils.json_utils import dumps_json, loads_json_list, parse_followers_count
from ..utils.source_classify import classify_source
from .departments import DEFAULT_DEPARTMENT, normalize_department_code
from .observation_enrichment import build_profile_snapshot, enrich_observation_payload, extract_shop_detail_fields
from .post_processing import canonical_source_type, find_existing_for_payload, record_creator_source

SHOP_SECTION_NAMES = (
    "Sales",
    "Video",
    "LIVE",
    "Followers",
    "Trends",
    "Rating",
    "Audience",
    "Example videos",
    "All videos",
    "Top brands",
    "Brand collaborations",
    "Collaboration metrics",
    "GMV by product category",
    "GMV per sales channel",
    "GMV per customer",
    "Categories",
    "Content quality",
)

RAW_QUEUE_LEAD_STATUSES = ("shop_list_seen", "shop_queue_cleared")
SHOP_SIGNAL_LINE_RE = re.compile(
    r"\b("
    r"gmv|gpm|commission|affiliate|collab|collaboration|sample|flat fee|sales|sold|"
    r"rating|followers|audience|female|male|video|live|category|beauty|skincare|"
    r"home|kitchen|baby|mom|pet|health|review|unboxing|haul|deal|shop|coupon|"
    r"creator agency|mcn"
    r")\b",
    re.IGNORECASE,
)
VALID_HANDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,99}$")


def ingest_observation(
    db: Session,
    payload: dict[str, Any],
    *,
    auto_process: bool = True,
    persist_raw: bool = True,
    observation_id: str | None = None,
) -> dict[str, Any]:
    """Persist + upsert. Returns a small dict describing what happened."""
    if not isinstance(payload, dict):
        raise ValueError("observation payload must be a dict")
    if payload.get("event_type") != "creator_observation":
        raise ValueError("event_type must be 'creator_observation'")
    if _is_source_video_seed_only(payload):
        return {
            "ok": True,
            "creator_id": None,
            "handle": ((payload.get("creator") or {}).get("handle") or None),
            "action": "skipped",
            "reason": "source_video_seed_only",
            "observation_id": observation_id,
        }

    payload = enrich_observation_payload(payload)
    creator_data = payload.get("creator") or {}
    handle = (creator_data.get("handle") or "").strip()

    platform = (payload.get("platform") or "tiktok").lower()
    department_code = normalize_department_code(payload.get("department_code"), default=DEFAULT_DEPARTMENT)
    collected_at = _parse_dt(payload.get("collected_at")) or datetime.now()
    raw_blob = dumps_json(payload)
    cid = creator_id_for(platform, handle) if handle else None
    creator = _find_existing_creator(db, platform, handle, cid, payload) if cid else find_existing_for_payload(db, platform, handle, payload)
    payload_has_contact = _has_ingestable_contact(creator_data)
    existing_has_contact = _creator_has_contact(creator) if creator is not None else False
    if handle and not payload_has_contact and _drops_no_contact_raw(platform):
        # X9 leads must only enter the server after the profile yields a contact
        # method. Keep TikTok Shop raw-only list rows, because Shop BD metrics
        # are still useful before detail/contact enrichment.
        return {
            "ok": True,
            "creator_id": None,
            "handle": handle,
            "action": "skipped",
            "reason": "missing_contact",
            "observation_id": observation_id,
        }

    if persist_raw:
        obs = RawObservation(
            id=new_id("obs"),
            platform=platform,
            department_code=department_code,
            source=payload.get("source") or "chrome_extension",
            worker_id=payload.get("worker_id"),
            account_id=payload.get("account_id"),
            search_keyword=payload.get("search_keyword"),
            lead_status=payload.get("lead_status"),
            raw_json=raw_blob,
            content_hash=content_hash(raw_blob),
            collected_at=collected_at,
        )
        db.add(obs)
        # Persist the immutable audit row after platform-specific pre-raw gates.
        # TikTok Shop still keeps raw-only list rows for later detail enrichment.
        db.commit()
        observation_id = obs.id

    if not handle:
        return {
            "ok": True,
            "creator_id": None,
            "handle": None,
            "action": "skipped",
            "reason": "missing_handle",
            "observation_id": observation_id,
        }

    if not payload_has_contact and not existing_has_contact:
        # Server-side gate: the extension only transports raw capture. After
        # enrichment, no-contact leads are removed from creators/pipeline here.
        return {
            "ok": True,
            "creator_id": None,
            "handle": handle,
            "action": "skipped",
            "reason": "missing_contact",
            "observation_id": observation_id,
        }

    new = False
    if creator is None:
        creator = Creator(id=cid, platform=platform, handle=handle, department_code=department_code)
        db.add(creator)
        new = True
    else:
        creator.platform = platform
        creator.handle = handle
    creator.department_code = department_code or creator.department_code

    _merge_fields(creator, creator_data, payload)
    creator.last_seen_at = datetime.now(timezone.utc)
    record_creator_source(
        db,
        creator,
        source_type=canonical_source_type(payload.get("platform"), payload.get("source") or "chrome_extension"),
        raw_observation_id=observation_id,
        worker_id=payload.get("worker_id"),
        account_id=payload.get("account_id"),
        observed_at=collected_at,
        metadata={"lead_status": payload.get("lead_status"), "search_keyword": payload.get("search_keyword")},
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        creator = _find_existing_creator(db, platform, handle, cid)
        if creator is None:
            raise
        new = False
        creator.platform = platform
        creator.handle = handle
        creator.department_code = department_code or creator.department_code
        _merge_fields(creator, creator_data, payload)
        creator.last_seen_at = datetime.now(timezone.utc)
        db.commit()

    creator_id = creator.id
    result = {
        "ok": True,
        "creator_id": creator_id,
        "handle": handle,
        "action": "inserted" if new else "updated",
        "observation_id": observation_id,
    }
    if auto_process:
        result["pipeline"] = _auto_process_creator(db, creator_id)
    return result


def reprocess_raw_observations(
    db: Session,
    *,
    limit: int = 1000,
    platform: str | None = "tiktok_shop",
    department_code: str | None = None,
    skip_invalid_handle_repairs: bool = True,
    auto_process: bool = True,
    unprocessed_only: bool = False,
    exclude_queue: bool = False,
) -> dict[str, Any]:
    """Replay stored raw observations through current server-side processors.

    This does not delete or rename existing creator rows. When
    skip_invalid_handle_repairs is true, old rows whose original raw handle was
    not a valid TikTok handle are skipped so this job does not perform the
    historical handle cleanup the user explicitly excluded.
    """
    limit = max(1, min(int(limit or 1000), 20000))
    q = select(RawObservation)
    if platform and platform != "all":
        q = q.where(RawObservation.platform == platform)
    if department_code:
        q = q.where(RawObservation.department_code == department_code)
    q = q.order_by(
        func.coalesce(RawObservation.collected_at, RawObservation.created_at).asc(),
        RawObservation.id.asc(),
    ).limit(limit)
    # CRITICAL: see pipeline.py:_repeat_discovery_for_creators for full
    # rationale. tldr: raw_json is ~142 KB/row, so a 20 000-row reprocess
    # would peak at ~2.8 GB of DOM text in Python. We stream + parse +
    # discard per row.
    #
    # Do NOT load ORM-mapped RawObservation objects here. The previous code
    # assigned `obs.raw_json = None` to free memory, which silently marked
    # every reprocessed row dirty; downstream db.commit() inside the
    # reprocess loop then wrote NULL back to the database, destroying the
    # raw JSON we just read. (Wiped 4000+ tiktok_shop captures on 2026-05-19/20.)
    #
    # Fetch only the columns we need as Core-level Rows and parse locally.
    light_q = select(RawObservation.id, RawObservation.raw_json)
    if platform and platform != "all":
        light_q = light_q.where(RawObservation.platform == platform)
    if department_code:
        light_q = light_q.where(RawObservation.department_code == department_code)
    if unprocessed_only:
        light_q = light_q.where(func.coalesce(RawObservation.process_status, "") == "")
    if exclude_queue:
        light_q = light_q.where(func.coalesce(RawObservation.lead_status, "").notin_(RAW_QUEUE_LEAD_STATUSES))
    light_q = light_q.order_by(
        func.coalesce(RawObservation.collected_at, RawObservation.created_at).asc(),
        RawObservation.id.asc(),
    ).limit(limit)
    stream = db.execute(light_q.execution_options(yield_per=200))

    prepared: list[tuple[str, dict[str, Any], bool]] = []
    scanned = 0
    counts = {
        "scanned": 0,
        "processed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "skipped_missing_contact": 0,
        "skipped_invalid_handle_source": 0,
        "skipped_missing_payload": 0,
    }
    errors: list[dict[str, str]] = []

    for obs_id, raw_json in stream:
        scanned += 1
        payload = _load_raw_payload(raw_json)
        # `raw_json` local var falls out of scope at loop end → GC reclaims
        # the ~142 KB blob. No ORM dirty bit set.
        if not payload:
            counts["skipped"] += 1
            counts["skipped_missing_payload"] += 1
            continue
        payload.setdefault("event_type", "creator_observation")
        if skip_invalid_handle_repairs and not _raw_payload_has_clean_handle(payload):
            counts["skipped"] += 1
            counts["skipped_invalid_handle_source"] += 1
            continue
        enriched = enrich_observation_payload(payload)
        has_contact = _has_ingestable_contact(enriched.get("creator") or {})
        prepared.append((obs_id, payload, has_contact))
    counts["scanned"] = scanned

    replay_order = [item for item in prepared if item[2]] + [item for item in prepared if not item[2]]
    for obs_id, payload, _has_contact in replay_order:
        try:
            result = ingest_observation(db, payload, auto_process=auto_process, persist_raw=False, observation_id=obs_id)
        except Exception as exc:
            counts["errors"] += 1
            errors.append({"observation_id": obs_id, "error": str(exc)})
            continue
        action = result.get("action")
        if action in {"inserted", "updated"}:
            counts["processed"] += 1
            counts[action] += 1
        elif action == "skipped":
            counts["skipped"] += 1
            if result.get("reason") == "missing_contact":
                counts["skipped_missing_contact"] += 1
    return {"ok": True, **counts, "error_samples": errors[:20]}


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


def _is_source_video_seed_only(payload: dict[str, Any]) -> bool:
    platform = str(payload.get("platform") or "tiktok").lower()
    return platform != "tiktok_shop" and payload.get("lead_status") == "source_video_seen"


def _drops_no_contact_raw(platform: str) -> bool:
    return platform == "tiktok"


def _normalize_handle_lookup(value: str | None) -> str:
    return str(value or "").strip().lstrip("@").lower()


def _find_existing_creator(db: Session, platform: str, handle: str, creator_id: str, payload: dict[str, Any] | None = None) -> Creator | None:
    creator = db.get(Creator, creator_id)
    if creator is not None:
        return creator

    platform_key = str(platform or "tiktok").strip().lower()
    handle_key = _normalize_handle_lookup(handle)
    if not handle_key:
        return None
    creator = db.scalar(
        select(Creator)
        .where(func.lower(func.trim(Creator.platform)) == platform_key)
        .where(func.lower(func.trim(Creator.handle)).in_([handle_key, f"@{handle_key}"]))
        .limit(1)
    )
    if creator is not None:
        return creator
    return find_existing_for_payload(db, platform, handle, payload or {})


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

    source_type = canonical_source_type(payload.get("platform"), payload.get("source") or "chrome_extension")
    current_status = normalize_current_status(c.get("current_status") or payload.get("current_status"))
    if current_status and (not creator.current_status or source_type == "bd"):
        creator.current_status = current_status

    store_assigned = (c.get("store_assigned") or payload.get("store_assigned") or "").strip()
    if store_assigned:
        creator.store_assigned = store_assigned

    owner_bd = (c.get("owner_bd") or c.get("bd_owner") or payload.get("owner_bd") or payload.get("bd_owner") or "").strip()
    if owner_bd and (not creator.owner_bd or source_type == "bd"):
        creator.owner_bd = owner_bd

    email = (c.get("email") or "").strip().lower() or None
    if not email and isinstance(c.get("emails"), list):
        email = next((str(v).strip().lower() for v in c["emails"] if str(v).strip()), None)
    if email:
        creator.email = email
        creator.has_email = 1
    elif creator.has_email is None:
        creator.has_email = 0

    if c.get("external_links") is not None:
        creator.external_links_json = dumps_json(
            _merge_unique_values(
                loads_json_list(creator.external_links_json)
                + loads_json_list(c["external_links"])
            )
        )

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

    snapshot = build_profile_snapshot(payload, c)
    if snapshot:
        creator.profile_snapshot_json = dumps_json(_merge_profile_snapshot(creator.profile_snapshot_json, snapshot))


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
    incoming_status = payload.get("lead_status")
    if incoming_status and not (creator.lead_status == "shop_profile_collected" and incoming_status == "shop_list_seen"):
        creator.lead_status = incoming_status

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
    detail_fields = shop.get("server_extracted") if isinstance(shop.get("server_extracted"), dict) else {}
    if not detail_fields:
        detail_fields = extract_shop_detail_fields(str(shop.get("raw_visible_text") or ""))
    for key, val in detail_fields.items():
        if val not in (None, ""):
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
    _merge_shop_detail_payload(metrics, shop, creator)
    metrics.setdefault("detail_captured", False)
    creator.tiktok_shop_json = dumps_json(metrics)


def _merge_shop_detail_payload(metrics: dict[str, Any], shop: dict[str, Any], creator: Creator) -> None:
    for key in ("profile", "metrics", "audience", "brands", "videos", "sections", "location_text"):
        value = shop.get(key)
        if value not in (None, "", [], {}):
            metrics[key] = _compact_json_value(value)

    profile = shop.get("profile") if isinstance(shop.get("profile"), dict) else {}
    bio = str(profile.get("bio") or "").strip()
    if bio and not creator.bio:
        creator.bio = bio[:1000]

    raw_text = str(shop.get("raw_visible_text") or "").strip()
    if not raw_text:
        return
    metrics["has_detail_text"] = True
    metrics["detail_text_excerpt"] = _compact_text(raw_text, 10000)
    signal_lines = _shop_signal_lines(raw_text)
    if signal_lines:
        metrics["detail_signal_lines"] = signal_lines
    sections = _shop_sections(raw_text)
    if sections:
        existing = metrics.get("detail_sections") if isinstance(metrics.get("detail_sections"), dict) else {}
        metrics["detail_sections"] = {**existing, **sections}


def _shop_sections(text: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    lower = text.lower()
    for name in SHOP_SECTION_NAMES:
        idx = lower.find(name.lower())
        if idx < 0:
            continue
        out[name] = {"visible_text": _compact_text(text[idx: idx + 3500], 1500)}
        if len(out) >= 10:
            break
    return out


def _shop_signal_lines(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in re.split(r"[\r\n]+", text):
        clean = re.sub(r"\s+", " ", line).strip()
        if len(clean) < 2 or len(clean) > 240:
            continue
        if not SHOP_SIGNAL_LINE_RE.search(clean):
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= 80:
            break
    return out


def _compact_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _compact_text(value, 2000)
    if isinstance(value, list):
        return [_compact_json_value(item) for item in value[:120]]
    if isinstance(value, dict):
        return {str(k): _compact_json_value(v) for k, v in list(value.items())[:120]}
    return value


def _compact_text(text: str, limit: int) -> str:
    clean = re.sub(r"[ \t]+", " ", str(text or ""))
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean[:limit]


def _has_ingestable_contact(c: dict[str, Any]) -> bool:
    email = (c.get("email") or "").strip()
    if not email and isinstance(c.get("emails"), list):
        email = next((str(v).strip() for v in c["emails"] if str(v).strip()), "")
    return has_contact_method(email, c.get("bio"), c.get("external_links"))


def _creator_has_contact(creator: Creator) -> bool:
    return has_contact_method(
        creator.email,
        creator.bio,
        loads_json_list(creator.external_links_json),
    )


def _load_raw_payload(raw_json: Any) -> dict[str, Any] | None:
    if isinstance(raw_json, dict):
        return dict(raw_json)
    if not raw_json:
        return None
    try:
        parsed = json.loads(str(raw_json))
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _raw_payload_has_clean_handle(payload: dict[str, Any]) -> bool:
    creator = payload.get("creator") if isinstance(payload.get("creator"), dict) else {}
    raw = str(creator.get("handle") or "").strip().lstrip("@")
    return bool(VALID_HANDLE_RE.fullmatch(raw))


def _merge_unique_values(values: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for value in values:
        if value is None or value == "":
            continue
        key = dumps_json(value) if isinstance(value, (dict, list)) else str(value).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _merge_profile_snapshot(existing_json: str | None, incoming: dict[str, Any]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if existing_json:
        try:
            parsed = json.loads(existing_json)
            if isinstance(parsed, dict):
                existing = parsed
        except (ValueError, TypeError):
            existing = {}
    merged = {**existing, **incoming}
    for key in ("emails", "external_links", "source_text_fields"):
        merged[key] = _merge_unique_values(loads_json_list(existing.get(key)) + loads_json_list(incoming.get(key)))
        if not merged[key]:
            merged.pop(key, None)
    return {key: value for key, value in merged.items() if value not in (None, "", [], {})}


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
