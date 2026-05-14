"""Initialize the SQLite database from schema.sql.

Usage:
    python scripts/db_init.py [--force]

--force: drop and recreate the database file (WARNING: data loss).
"""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
SCHEMA_PATH = ROOT / "schema.sql"


def init_db(force: bool = False) -> None:
    if DB_PATH.exists():
        if force:
            DB_PATH.unlink()
            for sidecar in (DB_PATH.with_suffix(".db-wal"), DB_PATH.with_suffix(".db-shm")):
                if sidecar.exists():
                    sidecar.unlink()
            print(f"[db_init] removed existing {DB_PATH.name}")
        else:
            print(f"[db_init] {DB_PATH.name} already exists. Use --force to recreate.")
            return

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(sql)
        con.commit()
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print(f"[db_init] created {len(rows)} tables: {[r[0] for r in rows]}")
    finally:
        con.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    init_db(force=args.force)
