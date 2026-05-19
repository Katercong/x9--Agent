from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.extension_command import ExtensionCommand
from ..models.extension_run_progress import ExtensionRunProgress
from ..models.extension_session import ExtensionSession
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, department_where, normalize_department_code
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json, parse_followers_count


router = APIRouter(prefix="/api/local/extension", tags=["extension"])


# Directory containing the merged extension (vendor v1.0.19 + relay).
# desktop/backend/routers/extension.py -> parents[2] = desktop/
_EXTENSION_DIR = Path(__file__).resolve().parents[2] / "chrome-extension"


@router.get("/download")
def download_extension() -> Response:
    """Stream the merged Chrome extension as a zip file for the user to install.

    Public (no auth) so anyone with dashboard access can grab it.
    Builds the zip on every request — picks up any local edits to the
    extension files without needing to pre-build.
    """
    if not _EXTENSION_DIR.is_dir():
        raise HTTPException(status_code=500, detail=f"extension dir missing: {_EXTENSION_DIR}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_EXTENSION_DIR.rglob("*")):
            if path.is_file():
                # Store relative path within the zip — the zip will extract to
                # a directory named after the zip's content (each file under
                # the root). chrome://extensions Load unpacked needs the
                # manifest.json at the root of the extracted folder.
                arcname = path.relative_to(_EXTENSION_DIR).as_posix()
                zf.write(path, arcname)

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="x9-tk-creator-extension.zip"',
        },
    )


# ---------------------------------------------------------------------------
# Heartbeat + status
# ---------------------------------------------------------------------------
def _as_aware_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


class HeartbeatIn(BaseModel):
    event_type: str = "extension_heartbeat"
    extension_id: str
    department_code: str | None = None
    extension_version: str | None = None
    worker_id: str
    account_id: str | None = None
    browser_profile: str | None = None
    current_url: str | None = None
    page_type: str | None = None
    tiktok_page_status: str | None = None
    tiktok_login_status: str | None = None
    active_tab_title: str | None = None
    timestamp: str | None = None


def _department_from_request(request: Request, fallback: str | None = None) -> str:
    if getattr(request.state, "current_user", None):
        return current_department_code(request) or DEFAULT_DEPARTMENT
    return normalize_department_code(fallback, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT


@router.post("/heartbeat")
def heartbeat(payload: HeartbeatIn, request: Request, db: Session = Depends(get_db)) -> dict:
    department_code = _department_from_request(request, payload.department_code)
    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == payload.worker_id))
    if sess is None:
        sess = ExtensionSession(id=new_id("ext"), extension_id=payload.extension_id, worker_id=payload.worker_id)
        db.add(sess)
    sess.extension_id = payload.extension_id
    sess.department_code = department_code
    sess.extension_version = payload.extension_version
    sess.account_id = payload.account_id
    sess.browser_profile = payload.browser_profile
    sess.current_url = payload.current_url
    sess.page_type = payload.page_type
    sess.tiktok_page_status = payload.tiktok_page_status
    sess.tiktok_login_status = payload.tiktok_login_status
    sess.active_tab_title = payload.active_tab_title
    sess.status = "online"
    sess.last_heartbeat_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "session_id": sess.id, "status": "online"}


@router.get("/status")
def extension_status(request: Request, db: Session = Depends(get_db)) -> dict:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.extension_offline_seconds)
    q = select(ExtensionSession)
    where_department = department_where(ExtensionSession, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    sessions = list(db.scalars(q.order_by(ExtensionSession.last_heartbeat_at.desc())).all())
    out = []
    for s in sessions:
        last = _as_aware_utc(s.last_heartbeat_at)
        online = bool(last and last >= threshold)
        out.append({
            "session_id": s.id,
            "department_code": s.department_code,
            "worker_id": s.worker_id,
            "account_id": s.account_id,
            "extension_version": s.extension_version,
            "current_url": s.current_url,
            "page_type": s.page_type,
            "tiktok_page_status": s.tiktok_page_status,
            "tiktok_login_status": s.tiktok_login_status,
            "online": online,
            "last_heartbeat_at": last.isoformat() if last else None,
        })
    return {"ok": True, "sessions": out, "any_online": any(s["online"] for s in out)}


# ---------------------------------------------------------------------------
# Commands queue (dashboard → extension)
# ---------------------------------------------------------------------------
class CommandPushIn(BaseModel):
    worker_id: str | None = None  # None = broadcast to any online worker
    command_type: str
    payload: dict | None = None
    department_code: str | None = None


class CommandAckIn(BaseModel):
    status: str = "done"  # done | error
    result: dict | None = None
    error_message: str | None = None


def _serialize_command(c: ExtensionCommand) -> dict:
    return {
        "id": c.id,
        "department_code": c.department_code,
        "worker_id": c.worker_id,
        "command_type": c.command_type,
        "payload_json": c.payload_json,
        "status": c.status,
        "result_json": c.result_json,
        "error_message": c.error_message,
        "created_at": _iso(c.created_at),
        "claimed_at": _iso(c.claimed_at),
        "completed_at": _iso(c.completed_at),
    }


@router.post("/commands")
def push_command(body: CommandPushIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Dashboard pushes a command for the extension to run."""
    department_code = _department_from_request(request, body.department_code)
    target = body.worker_id
    if not target:
        # Broadcast: pick the most recently seen online worker.
        threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.extension_offline_seconds)
        sess = db.scalar(
            select(ExtensionSession)
            .where(ExtensionSession.last_heartbeat_at >= threshold)
            .where(ExtensionSession.department_code == department_code)
            .order_by(ExtensionSession.last_heartbeat_at.desc())
        )
        if sess is None:
            raise HTTPException(status_code=409, detail="no online extension worker; specify worker_id explicitly")
        target = sess.worker_id

    cmd = ExtensionCommand(
        id=new_id("cmd"),
        department_code=department_code,
        worker_id=target,
        command_type=body.command_type,
        payload_json=dumps_json(body.payload or {}),
        status="pending",
    )
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    return {"ok": True, "command": _serialize_command(cmd)}


@router.get("/commands/pending")
def pending_commands(
    worker_id: str = Query(...),
    claim: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    """Extension polls this every few seconds. By default, claims every
    pending row (transitions pending -> claimed)."""
    q = (
        select(ExtensionCommand)
        .where(and_(ExtensionCommand.worker_id == worker_id, ExtensionCommand.status == "pending"))
        .order_by(ExtensionCommand.created_at)
        .limit(limit)
    )
    rows = list(db.scalars(q).all())
    if claim:
        now = datetime.now(timezone.utc)
        for r in rows:
            r.status = "claimed"
            r.claimed_at = now
        db.commit()
    return {"ok": True, "items": [_serialize_command(r) for r in rows]}


@router.post("/commands/{command_id}/ack")
def ack_command(command_id: str, body: CommandAckIn, db: Session = Depends(get_db)) -> dict:
    cmd = db.get(ExtensionCommand, command_id)
    if cmd is None:
        raise HTTPException(status_code=404, detail="command not found")
    cmd.status = body.status if body.status in {"done", "error"} else "done"
    cmd.completed_at = datetime.now(timezone.utc)
    cmd.result_json = dumps_json(body.result) if body.result is not None else None
    cmd.error_message = body.error_message
    db.commit()
    return {"ok": True, "command": _serialize_command(cmd)}


@router.get("/commands")
def list_commands(
    request: Request,
    worker_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    q = select(ExtensionCommand)
    where_department = department_where(ExtensionCommand, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    if worker_id:
        q = q.where(ExtensionCommand.worker_id == worker_id)
    if status:
        q = q.where(ExtensionCommand.status == status)
    q = q.order_by(ExtensionCommand.created_at.desc()).limit(limit)
    return {"ok": True, "items": [_serialize_command(r) for r in db.scalars(q).all()]}


# ---------------------------------------------------------------------------
# Auto-run progress (extension -> backend -> dashboard)
# ---------------------------------------------------------------------------
class RunProgressIn(BaseModel):
    worker_id: str
    department_code: str | None = None
    keyword: str | None = None
    step: str = "idle"
    running: bool = False
    stop_requested: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: int = 0
    profiles_visited: int = 0
    profiles_remaining: int = 0
    queue_size: int = 0
    leads_saved: int = 0
    skipped: int = 0
    scrolls_done: int = 0
    rest_breaks: int = 0
    current_handle: str | None = None
    current_action: str | None = None
    last_error: str | None = None
    settings: dict | None = None
    queue: list | None = None
    recent_leads: list | None = None


def _serialize_progress(p: ExtensionRunProgress) -> dict:
    return {
        "id": p.id,
        "department_code": p.department_code,
        "worker_id": p.worker_id,
        "keyword": p.keyword,
        "step": p.step,
        "running": bool(p.running),
        "stop_requested": bool(p.stop_requested),
        "started_at": _iso(p.started_at),
        "finished_at": _iso(p.finished_at),
        "elapsed_seconds": p.elapsed_seconds,
        "profiles_visited": p.profiles_visited,
        "profiles_remaining": p.profiles_remaining,
        "queue_size": p.queue_size,
        "leads_saved": p.leads_saved,
        "skipped": p.skipped,
        "scrolls_done": p.scrolls_done,
        "rest_breaks": p.rest_breaks,
        "current_handle": p.current_handle,
        "current_action": p.current_action,
        "last_error": p.last_error,
        "settings_json": p.settings_json,
        "queue_json": p.queue_json,
        "recent_leads_json": p.recent_leads_json,
        "updated_at": _iso(p.updated_at),
    }


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


@router.post("/run-progress")
def push_progress(body: RunProgressIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Extension pushes the latest auto-run state. Upserts on worker_id."""
    department_code = _department_from_request(request, body.department_code)
    p = db.scalar(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id == body.worker_id))
    if p is None:
        p = ExtensionRunProgress(id=new_id("rp"), worker_id=body.worker_id)
        db.add(p)
    p.department_code = department_code
    p.keyword = body.keyword
    p.step = body.step
    p.running = 1 if body.running else 0
    p.stop_requested = 1 if body.stop_requested else 0
    p.started_at = _parse_dt(body.started_at)
    p.finished_at = _parse_dt(body.finished_at)
    p.elapsed_seconds = body.elapsed_seconds
    p.profiles_visited = body.profiles_visited
    p.profiles_remaining = body.profiles_remaining
    p.queue_size = body.queue_size
    p.leads_saved = body.leads_saved
    p.skipped = body.skipped
    p.scrolls_done = body.scrolls_done
    p.rest_breaks = body.rest_breaks
    p.current_handle = body.current_handle
    p.current_action = body.current_action
    p.last_error = body.last_error
    p.settings_json = dumps_json(body.settings) if body.settings is not None else None
    p.queue_json = dumps_json(body.queue) if body.queue is not None else None
    p.recent_leads_json = dumps_json(body.recent_leads) if body.recent_leads is not None else None
    db.commit()
    return {"ok": True, "progress": _serialize_progress(p)}


@router.get("/run-progress")
def get_progress(
    request: Request,
    worker_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    department_code = _department_from_request(request)
    if worker_id:
        p = db.scalar(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id == worker_id))
        if p and p.department_code != department_code:
            p = None
        return {"ok": True, "progress": _serialize_progress(p) if p else None}
    q = select(ExtensionRunProgress)
    where_department = department_where(ExtensionRunProgress, department_code)
    if where_department is not None:
        q = q.where(where_department)
    rows = list(db.scalars(q.order_by(ExtensionRunProgress.updated_at.desc())).all())
    return {"ok": True, "items": [_serialize_progress(r) for r in rows]}


# ---------------------------------------------------------------------------
# v1.0.19 COMPATIBILITY ENDPOINTS
#
# The original `tiktok-creator-lead-browser` extension (v1.0.19 / v1.0.21)
# has a working auto-run loop that already handles search, scroll, profile
# open, scrape, filter and rate-limit. We preserve that flow verbatim
# and just accept its existing payload shapes here:
#
#   POST /api/local/extension/x9-compat/ingest-creators
#       { "items": [ { handle, platform, profile_url, display_name,
#                      followers, email, current_status, notes } ] }
#
#   POST /api/local/extension/launcher-heartbeat
#       { app, version, source, time, activeTab, page, counts,
#         runTimer, settings, latestLog }
#
# The first endpoint maps each item into a creator_observation and routes
# it through the v3 collector_service. The second updates the
# `extension_run_progress` row + `extension_sessions` row so the dashboard
# shows the same live state the side panel does.
# ---------------------------------------------------------------------------


def _parse_x9_notes(notes: str | None) -> dict[str, str]:
    """v1.0.19 packs metadata into a single 'notes' string of the form
    `keyword=foo filter=bar message=baz`. Pull the structured bits back."""
    out: dict[str, str] = {}
    if not notes:
        return out
    for part in notes.split():
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def _first_text(item: dict, *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _x9_links(item: dict):
    return (
        item.get("external_links")
        or item.get("links")
        or item.get("profile_links")
        or item.get("websites")
        or item.get("website")
        or []
    )


@router.post("/x9-compat/ingest-creators")
def x9_compat_ingest(body: dict, request: Request, db: Session = Depends(get_db)) -> dict:
    from ..services.collector_service import ingest_observation
    items = body.get("items") or []
    department_code = _department_from_request(request, body.get("department_code"))
    results: list[dict] = []
    for item in items:
        item_department = normalize_department_code(item.get("department_code"), default=department_code)
        handle = (item.get("handle") or "").strip()
        if not handle:
            results.append({"ok": False, "reason": "missing_handle"})
            continue
        notes_meta = _parse_x9_notes(item.get("notes"))
        keyword = notes_meta.get("keyword") or item.get("search_keyword") or None
        followers = item.get("followers", item.get("followers_count"))
        followers_raw = _first_text(item, "followers_raw", "followers_text", "followersLabel")
        if not followers_raw and isinstance(followers, str):
            followers_raw = followers
        followers_count = None
        if isinstance(followers, (int, float)):
            followers_count = int(followers)
        elif followers_raw:
            followers_count = parse_followers_count(followers_raw)
        visible_text = _first_text(item, "visible_text", "raw_visible_text", "profile_text", "raw_text", "text")
        external_links = _x9_links(item)
        current_status = item.get("current_status") or ("dropped" if notes_meta.get("filter") in {"no_email", "missing_contact"} else None)
        collected_at = (
            item.get("collected_at")
            or item.get("last_seen_at")
            or item.get("created_at")
            or item.get("time")
            or body.get("time")
            or body.get("timestamp")
            or datetime.now().isoformat(sep=" ", timespec="seconds")
        )
        observation = {
            "event_type": "creator_observation",
            "department_code": item_department,
            "platform": (item.get("platform") or "tiktok").lower(),
            "source": item.get("source") or "tiktok_creator_lead_browser",
            "worker_id": item.get("worker_id"),
            "account_id": item.get("account_id"),
            "search_keyword": keyword,
            "current_status": current_status,
            "lead_status": item.get("lead_status") or item.get("status") or ("skipped" if current_status == "dropped" else None),
            "filter_reason": item.get("filter_reason") or notes_meta.get("filter"),
            "filter_message": item.get("filter_message") or notes_meta.get("message"),
            "creator": {
                "handle": handle,
                "display_name": item.get("display_name") or item.get("nickname") or "",
                "profile_url": item.get("profile_url") or f"https://www.tiktok.com/@{handle}",
                "bio": item.get("bio"),
                "followers_raw": followers_raw,
                "followers_count": followers_count,
                "following_raw": item.get("following_raw"),
                "likes_raw": item.get("likes_raw"),
                "current_status": current_status,
                "email": item.get("email"),
                "emails": item.get("emails") or item.get("emails_json") or [],
                "external_links": external_links,
                "visible_text": visible_text,
                "source_url": item.get("source_url") or item.get("current_url"),
            },
            "source_video": (
                {
                    "video_url": item.get("source_video_url") or item.get("video_url"),
                    "title": item.get("source_video_title"),
                    "description": item.get("source_video_description"),
                    "hashtags": [],
                }
                if (item.get("source_video_url") or item.get("video_url")) else None
            ),
            "raw_profile": item.get("raw_profile") or {
                "username": item.get("handle") or item.get("username"),
                "nickname": item.get("display_name") or item.get("nickname"),
                "profile_url": item.get("profile_url"),
                "bio": item.get("bio"),
                "followers_raw": followers_raw,
                "followers_count": followers_count,
                "following_raw": item.get("following_raw"),
                "likes_raw": item.get("likes_raw"),
                "email": item.get("email"),
                "emails": item.get("emails") or item.get("emails_json") or [],
                "external_links": external_links,
                "visible_text": visible_text,
                "source_url": item.get("source_url") or item.get("current_url"),
            },
            "collected_at": collected_at,
        }
        try:
            r = ingest_observation(db, observation)
            r["dropped_by_extension"] = current_status == "dropped"
            r["filter_reason"] = notes_meta.get("filter")
            results.append(r)
        except ValueError as exc:
            results.append({"ok": False, "reason": str(exc)})
    return {"ok": True, "items": results, "count": len(results)}


def _coerce_dt(v: str | None):
    return _parse_dt(v) if v else None


@router.post("/launcher-heartbeat")
def launcher_heartbeat(body: dict, request: Request, db: Session = Depends(get_db)) -> dict:
    """v1.0.19 launcher-heartbeat. We mirror it into:
    * `extension_sessions` (so /extension/status shows the session)
    * `extension_run_progress` (so the dashboard shows live auto-run state)
    """
    settings_obj = body.get("settings") or {}
    run_timer = body.get("runTimer") or {}
    counts = body.get("counts") or {}
    page = body.get("page") or {}
    active_tab = body.get("activeTab") or {}

    # Resolve a worker_id. v1.0.19 doesn't send one explicitly — fall back
    # to the chrome runtime extensionId so each browser becomes a worker.
    worker_id = (
        body.get("worker_id")
        or body.get("extensionId")
        or "tiktok_creator_lead_browser"
    )
    department_code = _department_from_request(request, body.get("department_code"))

    # ---- session row (shows up in /extension/status) ----
    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
    if sess is None:
        sess = ExtensionSession(id=new_id("ext"), extension_id=body.get("app") or "tiktok_creator_lead_browser", worker_id=worker_id)
        db.add(sess)
    sess.extension_id = body.get("app") or sess.extension_id
    sess.department_code = department_code
    sess.extension_version = body.get("version")
    sess.current_url = active_tab.get("url")
    sess.active_tab_title = active_tab.get("title")
    sess.tiktok_page_status = "on_tiktok" if (page.get("isTikTok") or active_tab.get("isTikTok")) else "off_tiktok"
    sess.tiktok_login_status = (
        "not_logged_in" if (page.get("gate") or {}).get("type") == "login"
        else "logged_in" if page.get("isProfilePage") or page.get("isVideoPage") or page.get("isSearchVideoPage")
        else "unknown"
    )
    sess.page_type = (
        "creator_profile" if page.get("isProfilePage")
        else "video_page" if page.get("isVideoPage")
        else "search_results" if page.get("isSearchVideoPage")
        else None
    )
    sess.status = "online"
    sess.last_heartbeat_at = datetime.now(timezone.utc)

    # ---- run progress row (mirrors v1.0.19 counts/runTimer) ----
    p = db.scalar(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id == worker_id))
    if p is None:
        p = ExtensionRunProgress(id=new_id("rp"), worker_id=worker_id)
        db.add(p)
    p.department_code = department_code
    p.keyword = settings_obj.get("currentKeyword") or page.get("inferredSearchKeyword") or p.keyword
    p.running = 1 if run_timer.get("running") else 0
    p.stop_requested = 1 if settings_obj.get("autoStopRequested") else 0
    p.started_at = _coerce_dt(run_timer.get("started_at"))
    p.finished_at = _coerce_dt(run_timer.get("finished_at"))
    if isinstance(run_timer.get("elapsed_ms"), (int, float)):
        p.elapsed_seconds = int(run_timer["elapsed_ms"]) // 1000
    elif p.started_at and not p.finished_at:
        p.elapsed_seconds = int((datetime.now(timezone.utc) - p.started_at.replace(tzinfo=p.started_at.tzinfo or timezone.utc)).total_seconds())
    p.profiles_visited = int(counts.get("leads", 0)) + int(counts.get("skipped", 0))
    p.queue_size = int(counts.get("pending", 0))
    p.profiles_remaining = max(0, int(settings_obj.get("maxProfiles") or 0) - p.profiles_visited)
    p.leads_saved = int(counts.get("leads", 0))
    p.skipped = int(counts.get("skipped", 0))
    if p.running:
        p.step = "running"
    elif p.finished_at:
        p.step = "finished"
    else:
        p.step = "idle"
    latest_log = body.get("latestLog") or {}
    p.current_action = latest_log.get("message") or latest_log.get("event_type") or body.get("reason") or p.current_action
    p.settings_json = dumps_json(settings_obj)
    db.commit()
    return {"ok": True, "session_id": sess.id, "progress_id": p.id}
