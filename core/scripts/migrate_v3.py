"""Schema migration v3: llm_provider table for multi-LLM API key management.

Idempotent — safe to re-run.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS llm_provider (
    code              TEXT PRIMARY KEY,             -- 'anthropic', 'openai', 'deepseek', 'moonshot'...
    display_name      TEXT NOT NULL,
    type              TEXT NOT NULL                 -- 'anthropic' or 'openai_compat'
                      CHECK (type IN ('anthropic','openai_compat')),
    api_key           TEXT,                          -- plaintext (local-only DB)
    base_url          TEXT,
    default_model     TEXT,
    extra_headers     TEXT,                          -- JSON object, optional
    is_active         INTEGER NOT NULL DEFAULT 0,
    enabled           INTEGER NOT NULL DEFAULT 1,
    sort_order        INTEGER NOT NULL DEFAULT 0,
    last_tested_at    TEXT,
    last_test_status  TEXT,                          -- 'ok' / 'error'
    last_test_message TEXT,
    created_at        TEXT DEFAULT (datetime('now')),
    updated_at        TEXT DEFAULT (datetime('now'))
)
"""

SEED = [
    # (code, display_name, type, base_url, default_model, sort_order)
    ("anthropic", "Anthropic Claude", "anthropic",
     "https://api.anthropic.com/v1", "claude-sonnet-4-6", 1),
    ("openai", "OpenAI", "openai_compat",
     "https://api.openai.com/v1", "gpt-4o-mini", 2),
    ("deepseek", "DeepSeek", "openai_compat",
     "https://api.deepseek.com/v1", "deepseek-chat", 3),
]


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(CREATE_SQL)
    for code, name, typ, base, model, order in SEED:
        con.execute(
            "INSERT INTO llm_provider(code,display_name,type,base_url,default_model,sort_order) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET "
            "display_name=excluded.display_name, type=excluded.type, "
            "base_url=COALESCE(llm_provider.base_url, excluded.base_url), "
            "default_model=COALESCE(llm_provider.default_model, excluded.default_model), "
            "sort_order=excluded.sort_order",
            (code, name, typ, base, model, order)
        )
    con.commit()
    rows = con.execute("SELECT code, display_name, type, default_model, "
                       "CASE WHEN api_key IS NULL OR api_key='' THEN 'no key' ELSE 'has key' END "
                       "FROM llm_provider ORDER BY sort_order").fetchall()
    print(f"[migrate_v3] llm_provider table ready ({len(rows)} rows):")
    for r in rows:
        print(f"   {r[0]:12s} {r[1]:18s} {r[2]:14s} {r[3]:25s} {r[4]}")
    con.close()


if __name__ == "__main__":
    main()
