"""Schema migration v2: add video metric columns to outreach.

Idempotent — safe to re-run.
"""
from __future__ import annotations
import sqlite3
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
API_KEY_FILE = ROOT / ".api_key"


def add_col_if_missing(con: sqlite3.Connection, table: str, col_def: str) -> bool:
    col_name = col_def.split()[0]
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    if col_name in cols:
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    return True


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    added = 0
    for col in [
        "video_views INTEGER",
        "video_likes INTEGER",
        "video_comments INTEGER",
        "video_shares INTEGER",
        "metrics_updated_at TEXT",
    ]:
        if add_col_if_missing(con, "outreach", col):
            print(f"[migrate_v2] outreach.{col.split()[0]} added")
            added += 1
    con.commit()
    con.close()
    print(f"[migrate_v2] {added} new columns added")

    # Generate API key file if missing
    if not API_KEY_FILE.exists():
        key = secrets.token_urlsafe(32)
        API_KEY_FILE.write_text(key + "\n", encoding="ascii")
        print(f"[migrate_v2] generated new API key -> {API_KEY_FILE}")
        print(f"[migrate_v2] key value: {key}")
    else:
        print(f"[migrate_v2] API key file already exists at {API_KEY_FILE}")


if __name__ == "__main__":
    main()
