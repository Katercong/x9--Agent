"""PostgreSQL-backed LLM task Worker."""

from __future__ import annotations

import argparse
import os
import socket
import time

from .database import SessionLocal, init_db
from .services import claim_next_queued_run, persist_unexpected_claim_error, process_claimed_run, recover_expired_runs


def resolve_worker_id(explicit_worker_id: str | None = None) -> str:
    """Resolve a non-secret worker identity: CLI, environment, then hostname:pid."""

    candidate = explicit_worker_id if explicit_worker_id is not None else os.getenv("WORKER_ID")
    if candidate is not None and candidate.strip():
        worker_id = candidate.strip()
    else:
        worker_id = f"{socket.gethostname()}:{os.getpid()}"
    if len(worker_id) > 200:
        raise ValueError("worker_id must be at most 200 characters")
    return worker_id


def process_once(*, worker_id: str | None = None) -> str | None:
    """Use short PostgreSQL transactions for recovery, claim, and final writeback."""

    with SessionLocal() as db:
        try:
            recover_expired_runs(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    with SessionLocal() as db:
        try:
            claimed = claim_next_queued_run(db, worker_id=resolve_worker_id(worker_id))
            db.commit()
        except Exception:
            db.rollback()
            raise
    if claimed is None:
        return None
    try:
        process_claimed_run(claimed)
    except Exception as exc:
        persist_unexpected_claim_error(claimed, exc)
    return claimed.run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued ReplyChat LLM jobs")
    parser.add_argument("--once", action="store_true", help="process at most one queued job then exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="idle polling interval for continuous mode")
    parser.add_argument("--worker-id", help="optional operational identity; overrides WORKER_ID")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than 0")

    init_db()
    if args.once:
        process_once(worker_id=args.worker_id)
        return

    while True:
        if process_once(worker_id=args.worker_id) is None:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
