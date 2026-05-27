"""Background processor for queued raw extension captures."""
from __future__ import annotations

import logging
import threading
import time

from ..database import SessionLocal
from ..services.collector_service import reprocess_raw_observations

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_PROCESS_LOCK = threading.Lock()
_IDLE_INTERVAL_SECONDS = 1
_BUSY_INTERVAL_SECONDS = 0.1
_BATCH_SIZE = 200


def _run_once() -> int:
    if not _PROCESS_LOCK.acquire(blocking=False):
        return 0
    try:
        with SessionLocal() as db:
            result = reprocess_raw_observations(
                db,
                limit=_BATCH_SIZE,
                platform="all",
                queued_only=True,
                auto_process=False,
            )
            handled = int(result.get("processed") or 0) + int(result.get("skipped") or 0) + int(result.get("errors") or 0)
            if handled:
                log.info("raw_processor_scheduler: handled %d queued raw observations", handled)
            return handled
    except Exception as exc:
        log.warning("raw_processor_scheduler: processing failed: %s", exc)
        return 0
    finally:
        _PROCESS_LOCK.release()


def _run() -> None:
    while True:
        handled = _run_once()
        time.sleep(_BUSY_INTERVAL_SECONDS if handled else _IDLE_INTERVAL_SECONDS)


def start_raw_processor() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="raw-processor")
    thread.start()
    log.info("raw_processor_scheduler: started queued raw processor thread")
