from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .config import UI_DIR, settings
from .database import SessionLocal, init_db
from .models.request_log import RequestLog
from .utils import collector_queue_scheduler, log_scheduler, raw_processor_scheduler, session_cache, stats_scheduler
from .routers import (
    admin,
    analytics,
    app as app_router,
    auth,
    collector,
    creators,
    dashboard,
    data as data_router,
    db as db_router,
    export as export_router,
    extension,
    imports,
    outreach,
    post_process,
    process,
    recommendations,
    review_tasks,
    shared,
    v2 as v2_router,
)
from .services import auth_service
from .services.departments import SLUG_TO_CODE


app = FastAPI(title=settings.app_name, version=settings.system_version)
NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router.router)
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(db_router.router)
app.include_router(extension.router)
app.include_router(collector.router)
app.include_router(dashboard.router)
app.include_router(post_process.process_router)
app.include_router(process.router)
app.include_router(post_process.creators_router)
app.include_router(creators.router)
app.include_router(data_router.router)
app.include_router(review_tasks.router)
app.include_router(export_router.router)
app.include_router(imports.router)
app.include_router(post_process.outreach_router)
app.include_router(outreach.router)
app.include_router(analytics.router)
app.include_router(recommendations.router)
app.include_router(shared.router)
app.include_router(v2_router.router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    # Daily background prune of request_logs (was inline on every request,
    # which serialized writes behind a DELETE under load).
    log_scheduler.start_log_cleanup()
    # Stale TikTok Shop list rows are operational queue markers. Clear the
    # previous-day queue state once per day while preserving detail rows and
    # creator facts.
    collector_queue_scheduler.start_collector_queue_cleanup()
    # Raw extension captures are accepted quickly into PostgreSQL, then replayed
    # in small batches outside the request thread.
    raw_processor_scheduler.start_raw_processor()
    # Dashboard/API statistics are read much more often than they need to be
    # recomputed. Keep hot snapshots fresh once per minute in the background.
    stats_scheduler.start_stats_refresh()


PUBLIC_API_PATHS = {
    "/api/local/auth/me",
    "/api/local/auth/login",
    "/api/local/auth/register",
    "/api/local/auth/logout",
    "/api/local/outreach/gmail/client-info",
    "/api/local/outreach/gmail/auth-url",
    "/api/local/outreach/gmail/connect",
    "/api/local/outreach/gmail/callback",
    "/api/local/collector/observations",
    "/api/local/extension/heartbeat",
    "/api/local/extension/launcher-heartbeat",
    "/api/local/extension/x9-compat/ingest-creators",
    "/api/local/extension/run-progress",
    "/api/local/extension/download",
}
PUBLIC_API_PREFIXES = (
    "/api/local/extension/commands/pending",
    "/api/local/extension/commands/",
)


def _is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


def _admin_spa_role(path: str) -> str | None:
    if path == "/":
        return "root"
    if path.startswith("/a/"):
        return "super_admin"
    if path.startswith("/c/"):
        return "company_admin"
    if path.startswith("/d/"):
        return "department"
    if path.startswith("/preview"):
        # New v2 preview UI — accessible to any logged-in user.
        return "any"
    return None


def _home_for_user(user: dict) -> str:
    role = user.get("role")
    if role == "super_admin":
        return "/a/monitor"
    if role == "company_admin":
        return "/c/overview"
    if role == "department_admin":
        return "/d/dashboard"
    return "/portal/"


def _should_log_request(path: str) -> bool:
    if path in {"/health", "/favicon.ico"}:
        return False
    if path.startswith(("/assets/", "/portal/assets/", "/ui/assets/")):
        return False
    return True


def _write_request_log(method: str, path: str, status_code: int, duration_ms: int) -> None:
    """Append a single RequestLog row. Called from a BackgroundTask after the
    response is sent, so it never blocks the request thread.

    The 7-day prune used to run inline here; it's now a daily background job
    (utils/log_scheduler.py) so writes don't fight with DELETEs under load.
    """
    if not _should_log_request(path):
        return
    try:
        with SessionLocal() as db:
            db.add(
                RequestLog(
                    method=method[:10],
                    path=path[:300],
                    status_code=int(status_code),
                    duration_ms=max(0, int(duration_ms)),
                )
            )
            db.commit()
    except Exception:
        # Monitoring must never break the product path.
        pass


def _resolve_user_cached(token: str | None):
    """Token → user dict, hitting an in-process 60s LRU when possible.

    Avoids the per-request `SessionLocal() + DB query` overhead under multi-user
    load. Misses fall back to the real `current_user_from_token`.
    """
    if not token:
        return None
    cached = session_cache.get(token)
    if cached is not None:
        return cached
    with SessionLocal() as db:
        user = auth_service.current_user_from_token(db, token)
    session_cache.put(token, user)
    return user


@app.middleware("http")
async def require_dashboard_login(request, call_next):
    path = request.url.path
    started_at = time.perf_counter()
    user = None
    if path.startswith(("/api/local", "/api/v1", "/api/v2", "/a/", "/c/", "/d/", "/admin/", "/portal", "/preview")) or path == "/":
        token = request.cookies.get(auth_service.SESSION_COOKIE)
        # LRU cached resolve — skips DB on hot path for repeat polling
        # (`/api/local/auth/me`, dashboard refreshes, etc).
        user = _resolve_user_cached(token)
        request.state.current_user = user

    if path.startswith("/api/local"):
        if not _is_public_api_path(path) and user is None:
            return JSONResponse({"ok": False, "detail": "login required"}, status_code=401)

    if path.startswith(("/api/v1", "/api/v2")) and user is None:
        return JSONResponse({"ok": False, "detail": "login required"}, status_code=401)

    spa_role = _admin_spa_role(path)
    if spa_role:
        if user is None:
            login_url = "/login?next=" + str(request.url.path)
            return RedirectResponse(url=login_url, status_code=303)
        if spa_role == "root":
            return RedirectResponse(url=_home_for_user(user), status_code=303)
        if spa_role not in ("root", "any"):
            role = user.get("role")
            allowed = role == "department_admin" if spa_role == "department" else role == spa_role
            if not allowed:
                return RedirectResponse(url=_home_for_user(user), status_code=303)
    response = await call_next(request)
    # Write the log asynchronously — fire-and-forget so the response goes out
    # immediately. Previously this ran inline + did a 7-day DELETE on every
    # request, which serialized hot traffic behind table-level locks.
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    status_code = getattr(response, "status_code", 0) or 0
    try:
        # `get_running_loop()` is the modern, deprecation-safe variant (vs
        # the old `get_event_loop()`). It always returns the loop currently
        # running this middleware — exactly what we want.
        asyncio.get_running_loop().run_in_executor(
            None, _write_request_log, request.method, path, status_code, duration_ms
        )
    except Exception:
        # Never break the request path on logging issues.
        pass
    return response


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.system_version}


# ============================================================
# Root takeover: web/ React admin (4 roles × 24 pages) now serves "/".
# ============================================================
# Build: cd web && npm run build:root && npm run deploy:root
# Output: desktop/backend/ui/admin/   (base=/, clean URLs like /c/overview)
#
# 3 role spaces:
#   /c/*  公司管理员(老板视角)
#   /d/*  部门管理员(默认入口,参考图风格)
#   /a/*  超级管理员(系统运维)
#
# /login, /admin/, /workspace/{slug}/, /api/local/*, /ui/*, /portal/*, /landing
# are all preserved BEFORE the SPA fallbacks so they keep working.
ADMIN_DIR = UI_DIR / "admin"


def _admin_index() -> FileResponse:
    """Return the React admin index.html; fall back to legacy landing if missing."""
    candidate = ADMIN_DIR / "index.html"
    if candidate.is_file():
        return FileResponse(candidate, headers=NO_STORE_HEADERS)
    return FileResponse(UI_DIR / "landing.html", headers=NO_STORE_HEADERS)


@app.get("/")
def index() -> FileResponse:
    return _admin_index()


@app.get("/landing")
def legacy_landing() -> FileResponse:
    """One-off bookmark for the old marketing landing page."""
    return FileResponse(UI_DIR / "landing.html", headers=NO_STORE_HEADERS)


@app.get("/c/{full_path:path}")
def admin_company_spa(full_path: str) -> FileResponse:
    """SPA fallback for 公司管理员 routes (/c/overview, /c/revenue, ...)."""
    return _admin_index()


@app.get("/d/{full_path:path}")
def admin_department_spa(full_path: str) -> FileResponse:
    """SPA fallback for 部门管理员 routes (/d/dashboard, /d/creators, ...)."""
    return _admin_index()


@app.get("/a/{full_path:path}")
def admin_super_spa(full_path: str) -> FileResponse:
    """SPA fallback for 超级管理员 routes (/a/monitor, /a/users, ...)."""
    return _admin_index()


@app.get("/preview")
@app.get("/preview/{full_path:path}")
def admin_preview_spa(full_path: str = "") -> FileResponse:
    """SPA fallback for the v2 preview UI (/preview/pulse, /preview/me,
    /preview/creators, /preview/creators/:platform/:handle)."""
    return _admin_index()


@app.get("/assets/{asset_path:path}")
def admin_assets(asset_path: str) -> FileResponse:
    """Serve React's hashed JS/CSS bundles from desktop/backend/ui/admin/assets/."""
    candidate = ADMIN_DIR / "assets" / asset_path
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="asset not found")
    return FileResponse(candidate)


@app.get("/favicon.svg")
def admin_favicon() -> FileResponse:
    candidate = ADMIN_DIR / "favicon.svg"
    if candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404)


# ============================================================
# /api/v1/* reverse proxy → core backend on :18765
# web/ admin React calls /api/v1/data/creators etc; usx9.us only routes
# to desktop (:8000) via Cloudflare Tunnel, so desktop proxies through.
# ============================================================
CORE_API_BASE = "http://127.0.0.1:18765"
DEPARTMENT_SCOPED_RESOURCES = {"creators", "outreach", "staff"}
DEPARTMENT_METRIC_RESOURCES = {"business_metrics_daily"}
DEPARTMENT_QUERY_PREFIXES = ("creators_", "outreach_")
_DEPARTMENT_ID_CACHE: dict[str, str] = {}


def _department_scoped_user(user: dict | None) -> bool:
    return bool(user and user.get("role") in {"department_admin", "department_user"})


def _api_v1_resource(full_path: str) -> str | None:
    parts = full_path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "data":
        return parts[1]
    return None


def _api_v1_query_name(full_path: str) -> str | None:
    parts = full_path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "queries":
        return parts[1]
    return None


def _query_needs_department_scope(name: str | None) -> bool:
    return bool(name and name.startswith(DEPARTMENT_QUERY_PREFIXES))


def _path_needs_department_id(full_path: str) -> bool:
    resource = _api_v1_resource(full_path)
    if resource in DEPARTMENT_SCOPED_RESOURCES | DEPARTMENT_METRIC_RESOURCES:
        return True
    return _query_needs_department_scope(_api_v1_query_name(full_path))


async def _department_id_for_code(client: httpx.AsyncClient, code: str | None) -> str | None:
    if not code:
        return None
    cached = _DEPARTMENT_ID_CACHE.get(code)
    if cached:
        return cached
    r = await client.get(
        f"{CORE_API_BASE}/api/v1/data/departments",
        params={"code": code, "limit": 1},
    )
    if not r.is_success:
        return None
    try:
        items = r.json().get("items") or []
    except ValueError:
        return None
    if not items:
        return None
    department_id = str(items[0].get("id") or "")
    if department_id:
        _DEPARTMENT_ID_CACHE[code] = department_id
    return department_id or None


def _remove_params(params: list[tuple[str, str]], names: set[str]) -> list[tuple[str, str]]:
    return [(k, v) for k, v in params if k not in names]


def _scoped_api_v1_params(
    full_path: str,
    request: Request,
    user: dict | None,
    department_id: str | None,
) -> list[tuple[str, str]]:
    params = list(request.query_params.multi_items())
    if not _department_scoped_user(user):
        return params

    department_code = str(user.get("department_code") or "")
    resource = _api_v1_resource(full_path)
    query_name = _api_v1_query_name(full_path)

    if resource in DEPARTMENT_SCOPED_RESOURCES and department_id:
        params = _remove_params(params, {"department_id"})
        params.append(("department_id", department_id))
    elif resource == "departments" and department_code:
        params = _remove_params(params, {"code"})
        params.append(("code", department_code))
    elif resource in DEPARTMENT_METRIC_RESOURCES and department_code:
        params = _remove_params(params, {"scope_kind", "scope_id"})
        params.extend([("scope_kind", "department"), ("scope_id", department_code)])

    if _query_needs_department_scope(query_name) and department_id:
        params = _remove_params(params, {"department_id"})
        params.append(("department_id", department_id))

    return params


def _item_in_department(
    item: dict,
    *,
    resource: str | None,
    query_name: str | None,
    department_id: str | None,
    department_code: str | None,
) -> bool:
    if resource in DEPARTMENT_SCOPED_RESOURCES or _query_needs_department_scope(query_name):
        return str(item.get("department_id") or "") == str(department_id or "")
    if resource == "departments":
        return str(item.get("code") or "") == str(department_code or "")
    if resource in DEPARTMENT_METRIC_RESOURCES:
        return item.get("scope_kind") == "department" and str(item.get("scope_id") or "") == str(department_code or "")
    return True


def _scope_json_payload(
    full_path: str,
    payload,
    user: dict | None,
    department_id: str | None,
):
    if not _department_scoped_user(user):
        return payload
    resource = _api_v1_resource(full_path)
    query_name = _api_v1_query_name(full_path)
    department_code = str(user.get("department_code") or "")
    should_scope = (
        resource in (DEPARTMENT_SCOPED_RESOURCES | DEPARTMENT_METRIC_RESOURCES | {"departments"})
        or _query_needs_department_scope(query_name)
    )
    if not should_scope:
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        scoped = [
            item for item in payload["items"]
            if isinstance(item, dict)
            and _item_in_department(
                item,
                resource=resource,
                query_name=query_name,
                department_id=department_id,
                department_code=department_code,
            )
        ]
        out = dict(payload)
        out["items"] = scoped
        if len(scoped) != len(payload["items"]):
            out["total"] = len(scoped)
        return out
    if isinstance(payload, dict):
        return payload if _item_in_department(
            payload,
            resource=resource,
            query_name=query_name,
            department_id=department_id,
            department_code=department_code,
        ) else None
    return payload


@app.api_route(
    "/api/v1/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_core_api_v1(full_path: str, request: Request) -> Response:
    """Forward every /api/v1/* request to core backend on :18765."""
    url = f"{CORE_API_BASE}/api/v1/{full_path}"
    body = await request.body()
    user = getattr(request.state, "current_user", None)
    fwd_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            department_id = None
            if _department_scoped_user(user):
                department_id = await _department_id_for_code(client, user.get("department_code"))
                if _path_needs_department_id(full_path) and not department_id:
                    return JSONResponse(
                        {"ok": False, "detail": "department scope unavailable"},
                        status_code=503,
                    )
            r = await client.request(
                request.method, url,
                params=_scoped_api_v1_params(full_path, request, user, department_id),
                content=body or None,
                headers=fwd_headers,
            )
    except httpx.RequestError as exc:
        return JSONResponse(
            {"ok": False, "detail": f"core API unreachable: {exc}"},
            status_code=503,
        )
    resp_headers = {
        k: v for k, v in r.headers.items()
        if k.lower() not in ("transfer-encoding", "content-encoding", "content-length", "connection")
    }
    if request.method == "GET" and "application/json" in (r.headers.get("content-type") or ""):
        try:
            scoped_payload = _scope_json_payload(full_path, r.json(), user, department_id)
        except ValueError:
            scoped_payload = None
        if scoped_payload is None:
            return JSONResponse({"ok": False, "detail": "not found"}, status_code=404)
        return JSONResponse(scoped_payload, status_code=r.status_code, headers=resp_headers)
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)


@app.get("/admin/")
def admin_page(request: Request) -> RedirectResponse:
    """Compatibility bookmark: old /admin/ now lands on the role-bound React UI."""
    user = getattr(request.state, "current_user", None)
    if user:
        return RedirectResponse(url=_home_for_user(user), status_code=303)
    return RedirectResponse(url="/login?next=/admin/", status_code=303)


@app.get("/workspace/{department_slug}/")
def workspace_page(department_slug: str):
    if department_slug not in SLUG_TO_CODE:
        return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)
    # Merged: the legacy vanilla workspace UI is superseded by the React
    # portal. Old /workspace/{slug}/ links now land on the portal dashboard
    # (department scope comes from the session, not the slug).
    return RedirectResponse(url="/portal/dashboard", status_code=307)


@app.get("/ui/app.js")
def app_js() -> FileResponse:
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript", headers=NO_STORE_HEADERS)


@app.get("/ui")
def legacy_ui_redirect() -> RedirectResponse:
    return RedirectResponse(url="/portal/", status_code=307)


@app.get("/ui/")
def legacy_ui_slash_redirect() -> RedirectResponse:
    return RedirectResponse(url="/portal/", status_code=307)


# Serve legacy static assets from /ui/ for login/admin pages; /ui and /ui/
# themselves redirect to the React portal above.
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


# ---------- React portal (parallel UI, /portal/) ----------
# Build with: cd web-user && npm run build:deploy && npm run deploy
# (Outputs to desktop/backend/ui/portal/.)
# Existing /workspace/{slug}/ vanilla UI is untouched.
PORTAL_DIR = UI_DIR / "portal"


@app.get("/portal")
def portal_index_redirect() -> RedirectResponse:
    return RedirectResponse(url="/portal/")


@app.get("/portal/")
def portal_index() -> FileResponse:
    if not (PORTAL_DIR / "index.html").exists():
        return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)
    return FileResponse(PORTAL_DIR / "index.html", headers=NO_STORE_HEADERS)


@app.get("/portal/{full_path:path}")
def portal_spa(full_path: str) -> FileResponse:
    """SPA fallback for the React portal — serve real files when present,
    otherwise return index.html so React Router can handle the route."""
    if PORTAL_DIR.exists():
        candidate = PORTAL_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = PORTAL_DIR / "index.html"
        if index.exists():
            return FileResponse(index, headers=NO_STORE_HEADERS)
    return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)


# ============================================================
# (Legacy /portal/ paths above are kept untouched for old bookmarks.
#  The new web/ admin lives at / with /c/* /d/* /a/* SPA fallbacks
#  registered above. No catch-all — explicit routes only.)
# ============================================================
