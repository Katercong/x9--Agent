from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from ..config import settings


router = APIRouter(prefix="/api/local/app", tags=["app"])


@router.get("/status")
def status() -> dict:
    return {
        "ok": True,
        "service": settings.app_name,
        "env": settings.app_env,
        "system_version": settings.system_version,
        "score_version": settings.score_version,
        "tag_version": settings.tag_version,
        "rec_version": settings.rec_version,
        "started_at_pid": os.getpid(),
        "now": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/restart")
def restart() -> dict:
    """Best-effort signal — Electron main process tails this and restarts
    the python child. The process itself does not exit; that's the
    desktop's job."""
    return {"ok": True, "signal": "restart_requested"}
