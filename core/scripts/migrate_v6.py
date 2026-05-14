"""Schema migration v6: per-feature LLM binding.

Each AI feature (operations agent / outreach script generator / future ones)
can independently bind to a specific Provider + Model. Falls back to the
global is_active provider if no binding configured.

Idempotent.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS llm_feature (
    code           TEXT PRIMARY KEY,        -- 'agent', 'outreach_script', 'image_gen', ...
    display_name   TEXT NOT NULL,
    description    TEXT,
    provider_code  TEXT,                     -- nullable; null = use global active provider
    model          TEXT,                     -- nullable; null = use provider's default_model
    temperature    REAL,                     -- nullable; null = endpoint default
    max_tokens     INTEGER,                  -- nullable; null = endpoint default
    sort_order     INTEGER DEFAULT 0,
    enabled        INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (provider_code) REFERENCES llm_provider(code) ON DELETE SET NULL
)
"""

SEED = [
    # (code, display_name, description, sort_order)
    ("agent", "操作 AI 助手", "右下角悬浮的项目运维咨询 Agent", 1),
    ("outreach_script", "达人邀约话术生成", "按品类/达人/产品组合生成本地化邀约话术", 2),
]


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(CREATE_SQL)
    for code, name, desc, order in SEED:
        con.execute(
            "INSERT INTO llm_feature(code,display_name,description,sort_order) "
            "VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
            "display_name=excluded.display_name, description=excluded.description, "
            "sort_order=excluded.sort_order",
            (code, name, desc, order)
        )
    con.commit()
    rows = con.execute(
        "SELECT code, display_name, COALESCE(provider_code, '<fallback to global active>') AS p, "
        "COALESCE(model, '<provider default>') AS m, enabled "
        "FROM llm_feature ORDER BY sort_order"
    ).fetchall()
    print(f"[migrate_v6] llm_feature ready ({len(rows)} features):")
    for r in rows:
        print(f"   {r[0]:20s} {r[1]:24s} provider={r[2]:30s} model={r[3]:25s} enabled={r[4]}")
    con.close()


if __name__ == "__main__":
    main()
