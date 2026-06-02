from __future__ import annotations

import io
import json
import hashlib
import hmac
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.app_user import AppUser
from ..models.extension_command import ExtensionCommand
from ..models.extension_run_progress import ExtensionRunProgress
from ..models.extension_session import ExtensionSession
from ..models.creator_source import CreatorSource
from ..models.raw_observation import RawObservation
from ..services.departments import DEFAULT_DEPARTMENT, current_department_code, department_where, normalize_department_code
from ..services.departments import current_user as require_current_user
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json, parse_followers_count


router = APIRouter(prefix="/api/local/extension", tags=["extension"])
ADMIN_ROLES = {"super_admin", "company_admin", "department_admin"}


# Directory containing the TikTok creator extension (vendor v1.0.19 + relay).
# desktop/backend/routers/extension.py -> parents[2] = desktop/
_EXTENSION_DIR = Path(__file__).resolve().parents[2] / "chrome-extension"
# Merged foreign-trade extension (recruitment + Xiaohongshu/Douyin).
_FT_EXTENSION_DIR = Path(__file__).resolve().parents[2] / "foreign-trade-extension"
_FT_HELPER_DIR = Path(__file__).resolve().parents[2] / "foreign-trade-helper"


def _extension_dir_for_department(department_code: str | None) -> tuple[Path, str, str]:
    """Pick which extension to serve by department.

    foreign_trade → merged recruitment + XHS/Douyin extension.
    everything else (incl. cross_border) → the original TikTok extension.
    Returns (dir, zip filename, actor-config filename to personalize).
    """
    if normalize_department_code(department_code, default=None) == "foreign_trade" and _FT_EXTENSION_DIR.is_dir():
        return _FT_EXTENSION_DIR, "x9-foreign-trade-extension.zip", "ft_actor.js"
    return _EXTENSION_DIR, "x9-tk-creator-extension.zip", "x9_actor_config.js"


def _foreign_trade_readme() -> str:
    return "\n".join([
        "X9 外贸采集插件安装说明",
        "",
        "1. 解压本 zip。Chrome 扩展目录是 extension，请在 chrome://extensions 里选择“加载已解压的扩展程序”。",
        "2. 以 PowerShell 运行 helper/install_ft_helper.ps1。默认写入 https://usx9.us、foreign_trade、当前 helper 根目录。",
        "3. 打开插件侧边栏，确认 helper、后台、department、root 状态正常后开始采集。",
        "",
        "本地测试可运行：",
        'powershell -ExecutionPolicy Bypass -File ".\\helper\\install_ft_helper.ps1" -BackendUrl "http://127.0.0.1:8000"',
        "",
        "兼容入口：helper/install_companyleads.ps1 会转发到 install_ft_helper.ps1。",
        "配置文件仍写入 %LOCALAPPDATA%\\CompanyLeads\\config.json，以兼容旧 native messaging host 名称。",
    ]) + "\n"


def _should_skip_helper_file(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts or ".pytest_cache" in parts or ".venv" in parts:
        return True
    if "data" in parts and "runtime" in parts:
        return True
    return path.suffix.lower() in {".pyc", ".pyo", ".zip"}


def _ft_actor_config_js(payload: dict) -> str:
    """Personalize ft_actor.js with the downloading user's department + actor."""
    actor = payload.get("actor") or {}
    ft_data = {
        "department_code": (actor.get("department_code") or "foreign_trade"),
        "actor_user_id": payload.get("actor_user_id") or actor.get("id") or "",
        "actor_token": payload.get("actor_token") or "",
        "actor": actor,
        "downloaded_at": payload.get("downloaded_at") or "",
    }
    compat_payload = {
        "ok": bool(payload.get("ok")),
        "source": payload.get("source") or "download_user",
        "actor_user_id": ft_data["actor_user_id"],
        "actor": actor,
        "actor_token": ft_data["actor_token"],
        "downloaded_at": ft_data["downloaded_at"],
    }
    return (
        "globalThis.__X9_FT_ACTOR__ = "
        + json.dumps(ft_data, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
        + "globalThis.X9_BUNDLED_ACTOR_CONFIG = "
        + json.dumps(compat_payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )


def _extension_actor_token(actor_user_id: str, downloaded_at: str) -> str:
    secret = (
        os.getenv("X9_EXTENSION_ACTOR_TOKEN_SECRET")
        or settings.gmail_token_encryption_key
        or settings.super_admin_password
        or settings.app_name
    )
    message = f"{actor_user_id}|{downloaded_at}|{settings.app_name}"
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v1.{digest}"


def _actor_config_for_user(user: dict | None, *, source: str) -> dict:
    if not user:
        return {"ok": False, "source": source, "detail": "login_required"}
    if _is_admin_role(user):
        return {"ok": False, "source": source, "detail": "actor_binding_required"}
    actor = {
        "id": _actor_id(user),
        "username": user.get("username") or "",
        "display_name": user.get("display_name") or "",
        "email": user.get("email") or "",
        "role": user.get("role") or "",
        "department_code": user.get("department_code") or "",
    }
    if not actor["id"]:
        return {"ok": False, "source": source, "detail": "actor_user_id_missing"}
    downloaded_at = datetime.now(timezone.utc).isoformat()
    return {
        "ok": True,
        "source": source,
        "actor_user_id": actor["id"],
        "actor": actor,
        "actor_token": _extension_actor_token(actor["id"], downloaded_at),
        "downloaded_at": downloaded_at,
    }


def _actor_config_js(payload: dict) -> str:
    return (
        "globalThis.X9_BUNDLED_ACTOR_CONFIG = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )


@router.get("/download")
def download_extension(request: Request) -> Response:
    """Stream the merged Chrome extension as a zip file for the user to install.

    Public (no auth) so anyone with dashboard access can grab it.
    Builds the zip on every request — picks up any local edits to the
    extension files without needing to pre-build.
    """
    user = getattr(request.state, "current_user", None)
    department_code = current_department_code(request) if user else None
    ext_dir, zip_name, actor_file = _extension_dir_for_department(department_code)
    if not ext_dir.is_dir():
        raise HTTPException(status_code=500, detail=f"extension dir missing: {ext_dir}")

    actor_config = _actor_config_for_user(user, source="download_user")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        if zip_name == "x9-foreign-trade-extension.zip":
            if not _FT_HELPER_DIR.is_dir():
                raise HTTPException(status_code=500, detail=f"foreign trade helper dir missing: {_FT_HELPER_DIR}")
            for path in sorted(ext_dir.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(ext_dir).as_posix()
                    arcname = f"extension/{rel}"
                    if rel == actor_file:
                        # Foreign-trade extension: ft_actor.js with department + actor.
                        zf.writestr(arcname, _ft_actor_config_js(actor_config))
                    else:
                        zf.write(path, arcname)
            for path in sorted(_FT_HELPER_DIR.rglob("*")):
                if path.is_file() and not _should_skip_helper_file(path.relative_to(_FT_HELPER_DIR)):
                    zf.write(path, f"helper/{path.relative_to(_FT_HELPER_DIR).as_posix()}")
            zf.writestr("README_安装说明.txt", _foreign_trade_readme())
        else:
            for path in sorted(ext_dir.rglob("*")):
                if path.is_file():
                    # chrome://extensions "Load unpacked" needs manifest.json at the
                    # root of the extracted folder, so store paths relative to ext_dir.
                    arcname = path.relative_to(ext_dir).as_posix()
                    if arcname == "x9_actor_config.js":
                        # TikTok extension: bundled X9 actor config (legacy shape).
                        zf.writestr(arcname, _actor_config_js(actor_config))
                    elif arcname == actor_file:
                        zf.writestr(arcname, _ft_actor_config_js(actor_config))
                    else:
                        zf.write(path, arcname)

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Vary": "Cookie",
        },
    )


@router.get("/actor-config")
def actor_config(request: Request) -> dict:
    user = require_current_user(request)
    payload = _actor_config_for_user(user, source="portal_user")
    if not payload.get("ok"):
        raise HTTPException(status_code=409, detail=payload.get("detail") or "actor_binding_required")
    return payload


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
    source: str | None = None
    status: str | None = None
    running: bool | None = None
    current_action: str | None = None
    current_handle: str | None = None
    search_keyword: str | None = None
    hourly_limit: int | None = None
    hourly_used: int | None = None
    hourly_remaining: int | None = None
    next_resume_at: str | None = None
    last_error: str | None = None
    actor_user_id: str | None = None
    actor: dict | None = None


def _department_from_request(request: Request, fallback: str | None = None) -> str:
    if getattr(request.state, "current_user", None):
        return current_department_code(request) or DEFAULT_DEPARTMENT
    return normalize_department_code(fallback, default=DEFAULT_DEPARTMENT) or DEFAULT_DEPARTMENT


def _actor_id(user: dict | None) -> str | None:
    if not user:
        return None
    return str(user.get("id") or user.get("identity") or "").strip() or None


def _is_admin_user(user: dict | None) -> bool:
    return bool(user and user.get("entry_scope") == "admin" and user.get("role") in ADMIN_ROLES)


def _is_admin_role(user: dict | None) -> bool:
    return bool(user and user.get("role") in ADMIN_ROLES)


def _auto_bind_actor_id(user: dict | None) -> str | None:
    if not user or _is_admin_role(user):
        return None
    return _actor_id(user)


def _payload_actor_id(payload: dict | HeartbeatIn | None) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, HeartbeatIn):
        direct = payload.actor_user_id
        actor = payload.actor
    else:
        direct = payload.get("actor_user_id")
        actor = payload.get("actor")
    actor_id = str(direct or "").strip()
    if actor_id:
        return actor_id
    if isinstance(actor, dict):
        actor_id = str(actor.get("id") or actor.get("identity") or "").strip()
        if actor_id:
            return actor_id
    return None


def _trusted_payload_actor_id(db: Session, request: Request, actor_id: str | None) -> str | None:
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return None
    row = db.get(AppUser, actor_id)
    if row is None or int(row.is_active or 0) != 1:
        return None
    if row.role in ADMIN_ROLES:
        return None
    user = getattr(request.state, "current_user", None)
    department_code = current_department_code(request) if user else None
    if department_code is not None and normalize_department_code(row.department_code) != department_code:
        return None
    return row.id


def _heartbeat_actor_id(db: Session, request: Request, payload: dict | HeartbeatIn | None) -> str | None:
    return (
        _auto_bind_actor_id(getattr(request.state, "current_user", None))
        or _trusted_payload_actor_id(db, request, _payload_actor_id(payload))
    )


def _actor_summary(row: AppUser | None) -> dict | None:
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


def _json_obj(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _status_settings(**values) -> dict:
    return {key: value for key, value in values.items() if value is not None}


def _upsert_progress_from_status(
    db: Session,
    *,
    worker_id: str,
    department_code: str,
    status: str | None,
    running: bool | None,
    current_action: str | None,
    current_handle: str | None,
    search_keyword: str | None,
    hourly_limit: int | None,
    hourly_used: int | None,
    hourly_remaining: int | None,
    next_resume_at: str | None,
    last_error: str | None,
    source: str | None,
    extension_id: str | None,
    account_id: str | None,
) -> ExtensionRunProgress:
    p = db.scalar(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id == worker_id))
    if p is None:
        p = ExtensionRunProgress(id=new_id("rp"), worker_id=worker_id)
        db.add(p)
    existing_settings = _json_obj(p.settings_json)
    extra_settings = _status_settings(
        source=source,
        status=status,
        extension_id=extension_id,
        account_id=account_id,
        hourly_limit=hourly_limit,
        hourly_used=hourly_used,
        hourly_remaining=hourly_remaining,
        next_resume_at=next_resume_at,
    )
    p.department_code = department_code
    if search_keyword is not None:
        p.keyword = search_keyword
    if current_handle is not None:
        p.current_handle = current_handle
    if current_action is not None:
        p.current_action = current_action
    if last_error is not None:
        p.last_error = last_error
    if running is not None:
        p.running = 1 if running else 0
    if status:
        p.step = str(status)[:40]
    elif running is not None:
        p.step = "running" if running else "idle"
    p.settings_json = dumps_json({**existing_settings, **extra_settings})
    return p


def _session_actor_filter(request: Request, actor_user_id: str | None = None) -> str | None:
    user = getattr(request.state, "current_user", None)
    if _is_admin_user(user):
        requested = str(actor_user_id or "").strip()
        if requested in {"", "all", "*"}:
            return None
        return requested
    return _actor_id(user)


def _visible_session_filter(q, actor_filter: str | None):
    if not actor_filter:
        return q
    return q.where(or_(
        ExtensionSession.actor_user_id == actor_filter,
        ExtensionSession.actor_user_id.is_(None),
        ExtensionSession.actor_user_id == "",
    ))


@router.post("/heartbeat")
def heartbeat(payload: HeartbeatIn, request: Request, db: Session = Depends(get_db)) -> dict:
    department_code = _department_from_request(request, payload.department_code)
    actor_user_id = _heartbeat_actor_id(db, request, payload)
    actor_row = db.get(AppUser, actor_user_id) if actor_user_id else None
    if actor_row and actor_row.department_code:
        department_code = normalize_department_code(actor_row.department_code, default=DEFAULT_DEPARTMENT) or department_code
    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == payload.worker_id))
    if sess is None:
        sess = ExtensionSession(id=new_id("ext"), extension_id=payload.extension_id, worker_id=payload.worker_id)
        db.add(sess)
    sess.extension_id = payload.extension_id
    sess.department_code = department_code
    if actor_user_id:
        sess.actor_user_id = actor_user_id
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
    _upsert_progress_from_status(
        db,
        worker_id=payload.worker_id,
        department_code=department_code,
        status=payload.status,
        running=payload.running,
        current_action=payload.current_action,
        current_handle=payload.current_handle,
        search_keyword=payload.search_keyword,
        hourly_limit=payload.hourly_limit,
        hourly_used=payload.hourly_used,
        hourly_remaining=payload.hourly_remaining,
        next_resume_at=payload.next_resume_at,
        last_error=payload.last_error,
        source=payload.source,
        extension_id=payload.extension_id,
        account_id=payload.account_id,
    )
    db.commit()
    return {"ok": True, "session_id": sess.id, "status": "online"}


@router.get("/status")
def extension_status(
    request: Request,
    actor_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=settings.extension_offline_seconds)
    q = select(ExtensionSession)
    where_department = department_where(ExtensionSession, current_department_code(request))
    if where_department is not None:
        q = q.where(where_department)
    actor_filter = _session_actor_filter(request, actor_user_id)
    q = _visible_session_filter(q, actor_filter)
    sessions = list(db.scalars(q.order_by(ExtensionSession.last_heartbeat_at.desc())).all())
    actor_ids = {s.actor_user_id for s in sessions if s.actor_user_id}
    actors = {
        row.id: row
        for row in db.scalars(select(AppUser).where(AppUser.id.in_(actor_ids))).all()
    } if actor_ids else {}
    worker_ids = {s.worker_id for s in sessions if s.worker_id}
    progress_by_worker = {
        row.worker_id: row
        for row in db.scalars(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id.in_(worker_ids))).all()
    } if worker_ids else {}
    out = []
    for s in sessions:
        last = _as_aware_utc(s.last_heartbeat_at)
        online = bool(last and last >= threshold)
        actor = actors.get(s.actor_user_id or "")
        progress = progress_by_worker.get(s.worker_id)
        progress_settings = _json_obj(progress.settings_json if progress else None)
        out.append({
            "session_id": s.id,
            "department_code": s.department_code,
            "actor_user_id": s.actor_user_id,
            "actor": _actor_summary(actor),
            "worker_id": s.worker_id,
            "account_id": s.account_id,
            "source": progress_settings.get("source"),
            "status": progress_settings.get("status") or (progress.step if progress else s.status),
            "session_status": s.status,
            "running": bool(progress.running) if progress else False,
            "current_action": progress.current_action if progress else None,
            "current_handle": progress.current_handle if progress else None,
            "search_keyword": progress.keyword if progress else None,
            "hourly_limit": progress_settings.get("hourly_limit"),
            "hourly_used": progress_settings.get("hourly_used"),
            "hourly_remaining": progress_settings.get("hourly_remaining"),
            "next_resume_at": progress_settings.get("next_resume_at"),
            "last_error": progress.last_error if progress else None,
            "extension_version": s.extension_version,
            "current_url": s.current_url,
            "page_type": s.page_type,
            "tiktok_page_status": s.tiktok_page_status,
            "tiktok_login_status": s.tiktok_login_status,
            "online": online,
            "last_heartbeat_at": last.isoformat() if last else None,
        })
    return {"ok": True, "sessions": out, "any_online": any(s["online"] for s in out)}


class WorkerBindingIn(BaseModel):
    actor_user_id: str | None = None
    backfill: bool = False


def _backfill_worker_actor(
    db: Session,
    *,
    worker_id: str,
    actor_user_id: str,
    department_code: str,
) -> dict[str, int]:
    raw_stmt = (
        update(RawObservation)
        .where(RawObservation.worker_id == worker_id)
        .where(or_(RawObservation.actor_user_id.is_(None), RawObservation.actor_user_id == ""))
        .values(actor_user_id=actor_user_id, department_code=department_code)
    )
    source_stmt = (
        update(CreatorSource)
        .where(CreatorSource.worker_id == worker_id)
        .where(or_(CreatorSource.actor_user_id.is_(None), CreatorSource.actor_user_id == ""))
        .values(actor_user_id=actor_user_id, department_code=department_code)
    )
    raw_result = db.execute(raw_stmt)
    source_result = db.execute(source_stmt)
    return {
        "raw_observations": int(raw_result.rowcount or 0),
        "creator_sources": int(source_result.rowcount or 0),
    }


def _validate_target_actor(
    db: Session,
    request: Request,
    user: dict,
    actor_user_id: str | None,
) -> AppUser | None:
    is_admin = _is_admin_user(user)
    current_actor = _actor_id(user)
    target = str(actor_user_id or "").strip() or (current_actor if not is_admin else None)
    if not target:
        if is_admin:
            return None
        raise HTTPException(status_code=400, detail="actor_user_id is required")
    if not is_admin and target != current_actor:
        raise HTTPException(status_code=403, detail="cannot bind another user")

    actor = db.get(AppUser, target)
    if actor is None:
        raise HTTPException(status_code=404, detail="actor user not found")
    department_code = current_department_code(request)
    if department_code is not None and normalize_department_code(actor.department_code) != department_code:
        raise HTTPException(status_code=403, detail="actor user is outside current department")
    return actor


@router.post("/workers/{worker_id}/binding")
def bind_worker(
    worker_id: str,
    body: WorkerBindingIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user = require_current_user(request)
    if not worker_id.strip():
        raise HTTPException(status_code=400, detail="worker_id is required")
    if not _is_admin_user(user) and not body.actor_user_id:
        body.actor_user_id = _actor_id(user)

    actor = _validate_target_actor(db, request, user, body.actor_user_id)
    actor_user_id = actor.id if actor else None
    department_code = normalize_department_code(actor.department_code if actor else current_department_code(request), default=DEFAULT_DEPARTMENT)

    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
    if sess is None:
        sess = ExtensionSession(
            id=new_id("ext"),
            extension_id="manual_binding",
            worker_id=worker_id,
            department_code=department_code or DEFAULT_DEPARTMENT,
            status="offline",
        )
        db.add(sess)
    sess.actor_user_id = actor_user_id
    if department_code:
        sess.department_code = department_code

    backfill = {"raw_observations": 0, "creator_sources": 0}
    if actor_user_id and body.backfill:
        backfill = _backfill_worker_actor(
            db,
            worker_id=worker_id,
            actor_user_id=actor_user_id,
            department_code=department_code or DEFAULT_DEPARTMENT,
        )

    db.commit()
    return {
        "ok": True,
        "worker_id": worker_id,
        "actor_user_id": actor_user_id,
        "actor": _actor_summary(actor),
        "backfill": backfill,
    }


@router.get("/worker-self-bind")
def worker_self_bind(
    request: Request,
    worker_id: str = Query(...),
    backfill: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    """Bind a worker_id to the logged-in user, server-side.

    The Cloudflare-bypass upload path POSTs observations to the LAN desktop
    backend without the usx9.us session cookie, so those uploads cannot say
    who is collecting. The extension calls this GET against usx9.us while the
    user is logged into the portal — a GET traverses Cloudflare and carries
    the cookie — so the worker -> user link is recorded here.
    `_apply_worker_binding_attribution` then attributes every later cookieless
    upload that carries this worker_id."""
    worker_id = (worker_id or "").strip()
    if not worker_id:
        raise HTTPException(status_code=400, detail="worker_id is required")
    user = require_current_user(request)
    actor_user_id = _actor_id(user)
    if not actor_user_id:
        raise HTTPException(status_code=401, detail="login required")
    if _is_admin_role(user):
        raise HTTPException(status_code=409, detail="actor_binding_required")
    actor = _validate_target_actor(db, request, user, actor_user_id)
    department_code = normalize_department_code(
        actor.department_code if actor and actor.department_code else current_department_code(request),
        default=DEFAULT_DEPARTMENT,
    )
    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
    if sess is None:
        sess = ExtensionSession(
            id=new_id("ext"),
            extension_id="worker_self_bind",
            worker_id=worker_id,
            department_code=department_code,
            status="offline",
        )
        db.add(sess)
    sess.actor_user_id = actor_user_id
    if department_code:
        sess.department_code = department_code
    backfill_counts = {"raw_observations": 0, "creator_sources": 0}
    if backfill:
        backfill_counts = _backfill_worker_actor(
            db,
            worker_id=worker_id,
            actor_user_id=actor_user_id,
            department_code=department_code or DEFAULT_DEPARTMENT,
        )
    db.commit()
    return {
        "ok": True,
        "worker_id": worker_id,
        "actor_user_id": actor_user_id,
        "actor": _actor_summary(actor),
        "backfill": backfill_counts,
    }


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
    settings_obj = _json_obj(p.settings_json)
    return {
        "id": p.id,
        "department_code": p.department_code,
        "worker_id": p.worker_id,
        "source": settings_obj.get("source"),
        "status": settings_obj.get("status") or p.step,
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
        "hourly_limit": settings_obj.get("hourly_limit"),
        "hourly_used": settings_obj.get("hourly_used"),
        "hourly_remaining": settings_obj.get("hourly_remaining"),
        "next_resume_at": settings_obj.get("next_resume_at"),
        "settings": settings_obj,
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
    actor_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    department_code = _department_from_request(request)
    actor_filter = _session_actor_filter(request, actor_user_id)
    if worker_id:
        p = db.scalar(select(ExtensionRunProgress).where(ExtensionRunProgress.worker_id == worker_id))
        if p and p.department_code != department_code:
            p = None
        if p and actor_filter:
            sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
            if not sess or sess.actor_user_id != actor_filter:
                p = None
        return {"ok": True, "progress": _serialize_progress(p) if p else None}
    q = select(ExtensionRunProgress)
    where_department = department_where(ExtensionRunProgress, department_code)
    if where_department is not None:
        q = q.where(where_department)
    if actor_filter:
        scoped_workers = select(ExtensionSession.worker_id).where(ExtensionSession.actor_user_id == actor_filter)
        where_session_department = department_where(ExtensionSession, department_code)
        if where_session_department is not None:
            scoped_workers = scoped_workers.where(where_session_department)
        q = q.where(ExtensionRunProgress.worker_id.in_(scoped_workers))
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
    from ..services.upload_queue_cleanup import attach_queue_cleanup
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
            r = attach_queue_cleanup(r, observation, observation_id=r.get("observation_id"))
            results.append(r)
        except ValueError as exc:
            results.append({"ok": False, "reason": str(exc)})
    return attach_queue_cleanup(
        {"ok": True, "items": results, "count": len(results)},
        {"lead_status": "batch"},
        count=len(results),
    )


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
    actor_user_id = _heartbeat_actor_id(db, request, body)
    actor_row = db.get(AppUser, actor_user_id) if actor_user_id else None
    if actor_row and actor_row.department_code:
        department_code = normalize_department_code(actor_row.department_code, default=DEFAULT_DEPARTMENT) or department_code
    extension_id = body.get("extension_id") or body.get("app") or "tiktok_creator_lead_browser"

    # ---- session row (shows up in /extension/status) ----
    sess = db.scalar(select(ExtensionSession).where(ExtensionSession.worker_id == worker_id))
    if sess is None:
        sess = ExtensionSession(id=new_id("ext"), extension_id=extension_id, worker_id=worker_id)
        db.add(sess)
    sess.extension_id = extension_id or sess.extension_id
    sess.department_code = department_code
    if actor_user_id:
        sess.actor_user_id = actor_user_id
    sess.account_id = body.get("account_id") or settings_obj.get("accountId") or settings_obj.get("account_id") or sess.account_id
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
    p.keyword = body.get("search_keyword") or settings_obj.get("currentKeyword") or settings_obj.get("searchKeyword") or page.get("inferredSearchKeyword") or p.keyword
    running_value = body.get("running") if isinstance(body.get("running"), bool) else run_timer.get("running")
    p.running = 1 if running_value else 0
    p.stop_requested = 1 if settings_obj.get("autoStopRequested") else 0
    p.started_at = _coerce_dt(run_timer.get("started_at"))
    p.finished_at = _coerce_dt(run_timer.get("finished_at"))
    if isinstance(run_timer.get("elapsed_ms"), (int, float)):
        p.elapsed_seconds = int(run_timer["elapsed_ms"]) // 1000
    elif p.started_at and not p.finished_at:
        p.elapsed_seconds = int((datetime.now(timezone.utc) - p.started_at.replace(tzinfo=p.started_at.tzinfo or timezone.utc)).total_seconds())
    if body.get("source") == "tiktok_shop":
        detail_done = int(counts.get("detailDone", 0) or 0)
        detail_fail = int(counts.get("detailFail", 0) or 0)
        list_items = int(counts.get("listItems", 0) or 0)
        p.profiles_visited = detail_done + detail_fail
        p.queue_size = max(0, list_items - p.profiles_visited)
        p.profiles_remaining = max(0, int(settings_obj.get("taskCount") or list_items or 0) - p.profiles_visited)
        p.leads_saved = detail_done
        p.skipped = detail_fail
    else:
        p.profiles_visited = int(counts.get("leads", 0)) + int(counts.get("skipped", 0))
        p.queue_size = int(counts.get("pending", 0))
        p.profiles_remaining = max(0, int(settings_obj.get("maxProfiles") or 0) - p.profiles_visited)
        p.leads_saved = int(counts.get("leads", 0))
        p.skipped = int(counts.get("skipped", 0))
    if body.get("status"):
        p.step = str(body.get("status"))[:40]
    elif p.running:
        p.step = "running"
    elif p.finished_at:
        p.step = "finished"
    else:
        p.step = "idle"
    latest_log = body.get("latestLog") or {}
    p.current_handle = body.get("current_handle") or p.current_handle
    p.current_action = body.get("current_action") or latest_log.get("message") or latest_log.get("event_type") or body.get("reason") or p.current_action
    p.last_error = body.get("last_error") or p.last_error
    p.settings_json = dumps_json({
        **settings_obj,
        **_status_settings(
            source=body.get("source"),
            status=body.get("status"),
            extension_id=extension_id,
            account_id=sess.account_id,
            hourly_limit=body.get("hourly_limit"),
            hourly_used=body.get("hourly_used"),
            hourly_remaining=body.get("hourly_remaining"),
            next_resume_at=body.get("next_resume_at"),
        ),
    })
    db.commit()
    return {"ok": True, "session_id": sess.id, "progress_id": p.id}
