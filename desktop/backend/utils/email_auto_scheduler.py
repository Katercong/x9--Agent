"""Background processor for email-auto campaign jobs."""
from __future__ import annotations

import logging
import os
import threading
import time

from ..database import SessionLocal
from ..routers.email_auto import process_due_email_auto_jobs


log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_PROCESS_LOCK = threading.Lock()
_INITIAL_DELAY_SECONDS = 15


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _interval_seconds() -> int:
    return _env_int("X9_EMAIL_AUTO_INTERVAL_SECONDS", 60, minimum=15)


def _batch_limit() -> int:
    return _env_int("X9_EMAIL_AUTO_BATCH_LIMIT", 10, minimum=1)


def _process_once() -> None:
    if not _PROCESS_LOCK.acquire(blocking=False):
        return
    try:
        with SessionLocal() as db:
            results = process_due_email_auto_jobs(
                db,
                limit=_batch_limit(),
                department_code=None,
                user={"id": "email_auto_scheduler", "identity": "email_auto_scheduler"},
            )
        if results:
            sent = sum(1 for item in results if item.get("status") == "sent")
            drafts = sum(1 for item in results if item.get("status") == "draft_created")
            failed = sum(1 for item in results if item.get("status") == "failed")
            log.info(
                "email_auto_scheduler: processed %s due jobs, sent=%s drafts=%s failed=%s",
                len(results),
                sent,
                drafts,
                failed,
            )
    finally:
        _PROCESS_LOCK.release()


def _run() -> None:
    time.sleep(_INITIAL_DELAY_SECONDS)
    while True:
        started = time.perf_counter()
        try:
            _process_once()
        except Exception as exc:
            log.warning("email_auto_scheduler: processing failed: %s", exc)
        elapsed = time.perf_counter() - started
        time.sleep(max(5, _interval_seconds() - elapsed))


def start_email_auto_processor() -> None:
    if os.getenv("X9_DISABLE_EMAIL_AUTO_SCHEDULER") == "1":
        log.info("email_auto_scheduler: disabled by X9_DISABLE_EMAIL_AUTO_SCHEDULER=1")
        return
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="email-auto-processor")
    thread.start()
    log.info("email_auto_scheduler: started background processor")
