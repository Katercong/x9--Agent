from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import UI_DIR, settings
from .database import SessionLocal, init_db
from .routers import (
    admin,
    app as app_router,
    auth,
    collector,
    creators,
    db as db_router,
    export as export_router,
    extension,
    imports,
    outreach,
    process,
    review_tasks,
    shared,
)
from .services import auth_service
from .services.departments import SLUG_TO_CODE


app = FastAPI(title=settings.app_name, version=settings.system_version)
NO_STORE_HEADERS = {"Cache-Control": "no-store, max-age=0"}

# Gzip compression: shrinks app.js (~138 KB → ~35 KB) and the JSON API responses.
# minimum_size=512 skips small payloads where the framing overhead would dominate.
app.add_middleware(GZipMiddleware, minimum_size=512)

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
app.include_router(process.router)
app.include_router(creators.router)
app.include_router(review_tasks.router)
app.include_router(export_router.router)
app.include_router(imports.router)
app.include_router(outreach.router)
app.include_router(shared.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


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
}
PUBLIC_API_PREFIXES = (
    "/api/local/extension/commands/pending",
    "/api/local/extension/commands/",
)


def _is_public_api_path(path: str) -> bool:
    return path in PUBLIC_API_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_API_PREFIXES)


@app.middleware("http")
async def require_dashboard_login(request, call_next):
    path = request.url.path
    if path.startswith("/api/local"):
        with SessionLocal() as db:
            user = auth_service.current_user_from_token(
                db,
                request.cookies.get(auth_service.SESSION_COOKIE),
            )
        request.state.current_user = user
        if not _is_public_api_path(path) and user is None:
            return JSONResponse({"ok": False, "detail": "login required"}, status_code=401)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.system_version}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(UI_DIR / "landing.html", headers=NO_STORE_HEADERS)


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)


@app.get("/admin/")
def admin_page() -> FileResponse:
    return FileResponse(UI_DIR / "admin.html", headers=NO_STORE_HEADERS)


@app.get("/workspace/{department_slug}/")
def workspace_page(department_slug: str) -> FileResponse:
    if department_slug not in SLUG_TO_CODE:
        return FileResponse(UI_DIR / "login.html", headers=NO_STORE_HEADERS)
    return FileResponse(UI_DIR / "index.html", headers=NO_STORE_HEADERS)


@app.get("/ui/app.js")
def app_js() -> FileResponse:
    return FileResponse(UI_DIR / "app.js", media_type="application/javascript", headers=NO_STORE_HEADERS)


# Serve the desktop UI from /ui/. Electron points its BrowserWindow here.
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
