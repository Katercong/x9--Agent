"""Background scheduler for periodic maintenance.

Previously `_write_request_log` ran a DELETE for every incoming request to
prune the 7-day-old tail. That competes with hot read traffic and slows down
every single API call. We move it to a once-per-day background task.

If APScheduler isn't installed in this environment, fall back to a daemon
thread that wakes up every 6 hours — same effect, no dependency. The
fallback path is used in dev environments where the optional dep is missing.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

_STARTED = False
_LOCK = threading.Lock()


def _prune_request_logs() -> None:
    """Delete RequestLog rows older than 7 days, in 1k-row batches.

    A single bulk DELETE on a multi-million-row table forced both PG (giant
    transaction) and SQLAlchemy (statement buffering) to balloon, briefly
    spiking the desktop process to 17 GB before it released. Batching keeps
    every transaction small enough that neither side ever holds more than ~1k
    rows in memory. Each batch commits independently so an interrupted prune
    leaves the table in a sane state.

    Swallow exceptions — this is monitoring data, not business-critical.
    """
    try:
        from sqlalchemy import text
        from ..database import SessionLocal
        from ..models.request_log import RequestLog  # noqa: F401  (forces model registration)
    except Exception:
        return
    cutoff = datetime.utcnow() - timedelta(days=7)
    BATCH = 1000
    SAFETY_CAP = 5_000_000  # never loop more than this in one wake-up
    deleted_total = 0
    try:
        with SessionLocal() as db:
            # Use raw SQL with a CTE so PG can short-circuit cleanly when the
            # remaining tail is smaller than BATCH. RETURNING+ctid is the
            # standard pattern for safe batched DELETE in Postgres.
            dialect = db.bind.dialect.name if db.bind else "sqlite"
            for _ in range(SAFETY_CAP // BATCH):
                if dialect.startswith("postgresql"):
                    result = db.execute(
                        text(
                            """
                            WITH victim AS (
                              SELECT ctid FROM request_logs
                              WHERE ts < :cutoff
                              LIMIT :batch
                            )
                            DELETE FROM request_logs r USING victim v WHERE r.ctid = v.ctid
                            """
                        ),
                        {"cutoff": cutoff, "batch": BATCH},
                    )
                else:
                    # SQLite + others — rely on subquery rowid (SQLite) or fall
                    # back to a vanilla LIMIT-less DELETE if the dialect can't
                    # express a batched form.
                    result = db.execute(
                        text(
                            "DELETE FROM request_logs WHERE rowid IN ("
                            "SELECT rowid FROM request_logs WHERE ts < :cutoff LIMIT :batch"
                            ")"
                        ),
                        {"cutoff": cutoff, "batch": BATCH},
                    )
                db.commit()
                rows = result.rowcount or 0
                deleted_total += rows
                if rows < BATCH:
                    break
            log.info("log_scheduler: pruned %d RequestLog rows older than %s", deleted_total, cutoff)
    except Exception as exc:
        log.warning("log_scheduler: prune failed after %d rows: %s", deleted_total, exc)


def _run_periodically(interval_seconds: int) -> None:
    # First run shortly after startup so the table doesn't grow unbounded
    # between deploys, then on the regular interval.
    time.sleep(60)
    while True:
        _prune_request_logs()
        time.sleep(interval_seconds)


def start_log_cleanup() -> None:
    """Idempotent. Safe to call multiple times — only the first call starts a thread."""
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        _STARTED = True
    # Daily cleanup. We use a daemon thread rather than APScheduler to avoid
    # adding a runtime dependency for a 30-line cron job. The thread dies with
    # the process — exactly what we want for an embedded dashboard backend.
    thread = threading.Thread(
        target=_run_periodically,
        args=(24 * 3600,),
        daemon=True,
        name="request-log-cleanup",
    )
    thread.start()
    log.info("log_scheduler: started daily request-log cleanup thread")
