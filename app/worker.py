"""SQLite MVP 的单进程 LLM 任务 worker。"""

from __future__ import annotations

import argparse
import time

from .database import SessionLocal, init_db
from .services import claim_next_queued_run, process_claimed_run, recover_expired_runs


def process_once() -> str | None:
    """用三个短会话完成回收、领取和回写，模型调用期间不持有 SQLite 写事务。"""

    with SessionLocal() as db:
        try:
            recover_expired_runs(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    with SessionLocal() as db:
        try:
            claimed = claim_next_queued_run(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    if claimed is None:
        return None
    process_claimed_run(claimed)
    return claimed.run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued ReplyChat LLM jobs")
    parser.add_argument("--once", action="store_true", help="process at most one queued job then exit")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="idle polling interval for continuous mode")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be greater than 0")

    init_db()
    if args.once:
        process_once()
        return

    while True:
        if process_once() is None:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
