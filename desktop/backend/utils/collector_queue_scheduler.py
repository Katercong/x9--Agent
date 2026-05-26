"""Daily cleanup for stale collector queue markers."""
from __future__ import annotations

import logging
import threading
import time

from ..database import SessionLocal
from ..services.collection_stats_service import clear_stale_shop_queue_rows

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()


def _cleanup_once() -> None:
    try:
        with SessionLocal() as db:
            result = clear_stale_shop_queue_rows(db)
        log.info(
            "collector_queue_scheduler: cleared %d stale queue rows before %s",
            result.get("cleared", 0),
            result.get("cutoff"),
        )
    except Exception as exc:
        log.warning("collector_queue_scheduler: cleanup failed: %s", exc)


def _run_periodically(interval_seconds: int) -> None:
    time.sleep(60)
    while True:
        _cleanup_once()
        time.sleep(interval_seconds)


def start_collector_queue_cleanup() -> None:
    """Idempotent daily queue cleanup thread."""
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(
        target=_run_periodically,
        args=(24 * 3600,),
        daemon=True,
        name="collector-queue-cleanup",
    )
    thread.start()
    log.info("collector_queue_scheduler: started daily queue cleanup thread")
