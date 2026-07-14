"""SQLite MVP 的单进程 LLM 任务 worker。"""

from __future__ import annotations

import argparse
import time

from .database import SessionLocal, init_db
from .services import process_next_queued_run


def process_once() -> str | None:
    """使用独立会话处理最早的一条待执行任务，并返回任务 ID。"""

    with SessionLocal() as db:
        try:
            run = process_next_queued_run(db)
            db.commit()
            return run.id if run is not None else None
        except Exception:
            # 异常时回滚领取状态，任务会保持 queued 供人工检查或下次 worker 处理。
            db.rollback()
            raise


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
