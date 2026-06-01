"""Background Gmail reply sync loop for creator outreach tracking."""
from __future__ import annotations

import logging
import os
import threading
import time

from ..database import SessionLocal
from ..services import gmail_sync_service


log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()
_INTERVAL_SECONDS = gmail_sync_service.SYNC_INTERVAL_MINUTES * 60
_INITIAL_DELAY_SECONDS = 20


def _sync_once() -> None:
    with SessionLocal() as db:
        result = gmail_sync_service.sync_all_authorized_mailboxes(db)
        totals = result.get("totals") or {}
        log.info(
            "gmail_sync_scheduler: checked %s threads, stored %s replies and %s bounces across %s accounts",
            totals.get("threads_checked", 0),
            totals.get("new_replies", 0),
            totals.get("new_bounces", 0),
            totals.get("accounts", 0),
        )


def _run() -> None:
    time.sleep(_INITIAL_DELAY_SECONDS)
    while True:
        started = time.perf_counter()
        try:
            _sync_once()
        except Exception as exc:
            log.warning("gmail_sync_scheduler: sync failed: %s", exc)
        elapsed = time.perf_counter() - started
        time.sleep(max(30, _INTERVAL_SECONDS - elapsed))


def start_gmail_reply_sync() -> None:
    if os.getenv("X9_DISABLE_GMAIL_SYNC_SCHEDULER") == "1":
        log.info("gmail_sync_scheduler: disabled by X9_DISABLE_GMAIL_SYNC_SCHEDULER=1")
        return
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    thread = threading.Thread(target=_run, daemon=True, name="gmail-reply-sync")
    thread.start()
    log.info("gmail_sync_scheduler: started %ss reply sync thread", _INTERVAL_SECONDS)
