"""Background precompute loop for dashboard statistics."""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select

from ..database import SessionLocal
from ..models.app_user import AppUser
from ..services import auth_service

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_INTERVAL_SECONDS = 60


def _refresh_once() -> None:
    with SessionLocal() as db:
        users = list(db.scalars(select(AppUser).order_by(AppUser.role.asc(), AppUser.username.asc())).all())
        auth_service.refresh_user_activity_stats(db, users)


def _run() -> None:
    while True:
        started = time.perf_counter()
        try:
            _refresh_once()
            duration_ms = int((time.perf_counter() - started) * 1000)
            log.info("stats_scheduler: refreshed dashboard stats in %d ms", duration_ms)
        except Exception as exc:
            log.warning("stats_scheduler: refresh failed: %s", exc)
        elapsed = time.perf_counter() - started
        time.sleep(max(5, _INTERVAL_SECONDS - elapsed))


def start_stats_refresh() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="stats-refresh")
    thread.start()
    log.info("stats_scheduler: started 60s dashboard stats refresh thread")
