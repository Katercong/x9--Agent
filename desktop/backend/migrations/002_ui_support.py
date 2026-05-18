"""002_ui_support: tables backing the new React portal at /portal/.

Adds three tables (additive, idempotent), portable across SQLite and PostgreSQL:
  - assistant_conversations: AI 助手会话(每次刷新前的多轮对话留痕)
  - assistant_messages: 每条 user / assistant 消息
  - keyword_today_trend: 每小时采集计数,用于 /collection 页 24h 趋势曲线

Safe to run multiple times.

Usage:
  py -3.11 -m desktop.backend.migrations.002_ui_support
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from desktop.backend.database import engine  # noqa: E402


def main() -> int:
    dialect = engine.dialect.name
    # PostgreSQL uses GENERATED ... AS IDENTITY; SQLite uses AUTOINCREMENT.
    if dialect == "postgresql":
        id_col = "id BIGSERIAL PRIMARY KEY"
    else:
        id_col = "id INTEGER PRIMARY KEY AUTOINCREMENT"

    stmts = [
        # ---------- 1. assistant_conversations ----------
        """
        CREATE TABLE IF NOT EXISTS assistant_conversations (
            id              VARCHAR(80) PRIMARY KEY,
            user_id         INTEGER,
            department_code VARCHAR(40),
            title           VARCHAR(200),
            provider        VARCHAR(40),
            model           VARCHAR(80),
            message_count   INTEGER NOT NULL DEFAULT 0,
            last_message_at TIMESTAMP,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_assistant_conv_user ON assistant_conversations (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_assistant_conv_dept ON assistant_conversations (department_code)",

        # ---------- 2. assistant_messages ----------
        f"""
        CREATE TABLE IF NOT EXISTS assistant_messages (
            {id_col},
            conversation_id VARCHAR(80) NOT NULL,
            role            VARCHAR(20) NOT NULL,
            content         TEXT NOT NULL,
            tokens_in       INTEGER,
            tokens_out      INTEGER,
            elapsed_ms      INTEGER,
            error           TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_assistant_msg_conv ON assistant_messages (conversation_id, created_at)",

        # ---------- 3. keyword_today_trend ----------
        f"""
        CREATE TABLE IF NOT EXISTS keyword_today_trend (
            {id_col},
            department_code VARCHAR(40),
            day             VARCHAR(10) NOT NULL,
            hour            INTEGER NOT NULL,
            observations    INTEGER NOT NULL DEFAULT 0,
            new_creators    INTEGER NOT NULL DEFAULT 0,
            new_recs        INTEGER NOT NULL DEFAULT 0,
            new_reviews     INTEGER NOT NULL DEFAULT 0,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(department_code, day, hour)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_kw_today_day ON keyword_today_trend (day)",
    ]

    print(f"[002_ui_support] dialect={dialect}, applying {len(stmts)} DDL statements...")
    applied = 0
    failed = 0
    for sql in stmts:
        preview = " ".join(sql.split())[:80]
        # 每条 DDL 独立事务,失败不影响后续
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
            print(f"  [OK]   {preview}...")
            applied += 1
        except Exception as e:
            err = str(e).split("\n")[0]
            print(f"  [FAIL] {preview}... -> {err}")
            failed += 1

    print(f"[002_ui_support] done. applied={applied} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
