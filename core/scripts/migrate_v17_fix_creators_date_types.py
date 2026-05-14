"""migrate_v17: fix creators.* date columns from TEXT to TIMESTAMP.

Background:
  When migrate_sqlite_to_postgres.py created the postgres tables from SQLite,
  it stored SQLite date columns as TEXT. SQLAlchemy's Creator model declares
  these same columns as DateTime, so psycopg returns strings, then
  `.isoformat()` calls in routers/creators.py raise AttributeError.

  Effect on dashboard: /api/local/creators/recommended fails with 500,
  Desktop dashboard "Database" indicator shows "Abnormal" (异常).

Fix: ALTER each affected column to TIMESTAMP, casting the string contents.

Idempotent: safe to re-run; ALTER on already-TIMESTAMP columns is skipped via
information_schema check.

Usage:
  py core/scripts/migrate_v17_fix_creators_date_types.py
  py core/scripts/migrate_v17_fix_creators_date_types.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg
from psycopg import sql


DEFAULT_PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)

# Columns on `creators` that the SQLAlchemy Creator model declares as DateTime
# but the DB stores as TEXT. Order matters only for readability.
CREATORS_DATE_COLUMNS = [
    "collected_at",
    "last_seen_at",
    "scored_at",
    "tagged_at",
    "recommended_at",
    "created_at",
    "updated_at",
]


def column_type(cur: psycopg.Cursor, table: str, column: str) -> str | None:
    cur.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    row = cur.fetchone()
    return row[0] if row else None


def alter_to_timestamp(cur: psycopg.Cursor, table: str, column: str) -> str:
    """Returns 'altered' or 'skipped:<reason>'."""
    typ = column_type(cur, table, column)
    if typ is None:
        return f"skipped:column-missing"
    if typ in ("timestamp without time zone", "timestamp with time zone"):
        return "skipped:already-timestamp"

    # Cast via NULLIF to allow empty strings.
    stmt = sql.SQL(
        "ALTER TABLE {} ALTER COLUMN {} TYPE TIMESTAMP "
        "USING NULLIF({}, '')::timestamp"
    ).format(
        sql.Identifier(table),
        sql.Identifier(column),
        sql.Identifier(column),
    )
    cur.execute(stmt)
    return "altered"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"[migrate_v17] connecting to {args.dsn.split('@')[-1]}")
    with psycopg.connect(args.dsn) as con:
        with con.cursor() as cur:
            for col in CREATORS_DATE_COLUMNS:
                result = alter_to_timestamp(cur, "creators", col)
                print(f"[migrate_v17] creators.{col}: {result}")

            if args.dry_run:
                con.rollback()
                print("[migrate_v17] DRY RUN — rolled back")
                return 0

            con.commit()
            print("[migrate_v17] committed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
