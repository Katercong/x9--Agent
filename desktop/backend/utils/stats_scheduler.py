"""Background precompute loop for dashboard statistics."""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import select

from ..database import SessionLocal
from ..models.app_user import AppUser
from ..services import auth_service
from ..services.collection_stats_service import (
    UNASSIGNED_ACTOR,
    refresh_actor_collection_stats_map,
    refresh_source_stats,
)

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_INTERVAL_SECONDS = 60


def _refresh_once() -> None:
    with SessionLocal() as db:
        users = list(db.scalars(select(AppUser).order_by(AppUser.role.asc(), AppUser.username.asc())).all())
        auth_service.refresh_user_activity_stats(db, users)

        collection_users = [
            row.id
            for row in users
            if row.role == auth_service.DEPARTMENT_USER_ROLE and int(row.is_active or 0) == 1 and row.id
        ]
        refresh_actor_collection_stats_map(db, collection_users, department_code=None)
        refresh_source_stats(db, department_code=None, actor_filter=None)
        refresh_source_stats(db, department_code=None, actor_filter=UNASSIGNED_ACTOR)


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
