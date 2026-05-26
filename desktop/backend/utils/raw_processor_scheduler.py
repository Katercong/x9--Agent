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
_INTERVAL_SECONDS = 10
_BATCH_SIZE = 50


def _run_once() -> None:
    if not _PROCESS_LOCK.acquire(blocking=False):
        return
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
    except Exception as exc:
        log.warning("raw_processor_scheduler: processing failed: %s", exc)
    finally:
        _PROCESS_LOCK.release()


def _run() -> None:
    while True:
        started = time.perf_counter()
        _run_once()
        elapsed = time.perf_counter() - started
        time.sleep(max(1, _INTERVAL_SECONDS - elapsed))


def start_raw_processor() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="raw-processor")
    thread.start()
    log.info("raw_processor_scheduler: started queued raw processor thread")
