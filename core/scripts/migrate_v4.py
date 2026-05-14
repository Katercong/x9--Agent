"""Schema migration v4: _meta_query table.

Allows storing named queries in the DB (instead of code), so张 can add new
queries via API without restarting the server / editing Python.

Built-in queries from app/registry.py NAMED_QUERIES are also seeded here on
first run. Editing a built-in via the API creates an override row that
shadows the code definition.

Idempotent.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS _meta_query (
    name        TEXT PRIMARY KEY,
    description TEXT,
    sql         TEXT NOT NULL,
    params      TEXT,                          -- JSON array of [name,type,default]
    is_builtin  INTEGER NOT NULL DEFAULT 0,    -- 1 = seeded from code (do not delete; override allowed)
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
)
"""


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(CREATE_SQL)

    # Seed built-in queries from registry
    import sys
    sys.path.insert(0, str(ROOT))
    from app.registry import NAMED_QUERIES

    for q in NAMED_QUERIES.values():
        con.execute(
            "INSERT INTO _meta_query(name,description,sql,params,is_builtin) "
            "VALUES(?,?,?,?,1) "
            "ON CONFLICT(name) DO UPDATE SET "
            "  description=CASE WHEN _meta_query.is_builtin=1 THEN excluded.description ELSE _meta_query.description END, "
            "  sql=CASE WHEN _meta_query.is_builtin=1 THEN excluded.sql ELSE _meta_query.sql END, "
            "  params=CASE WHEN _meta_query.is_builtin=1 THEN excluded.params ELSE _meta_query.params END",
            (q.name, q.description, q.sql, json.dumps(q.params))
        )
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM _meta_query").fetchone()[0]
    print(f"[migrate_v4] _meta_query has {n} queries")
    con.close()


if __name__ == "__main__":
    main()
