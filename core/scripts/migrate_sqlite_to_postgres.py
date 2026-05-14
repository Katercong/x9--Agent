from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql


DEFAULT_PG_DSN = "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db"
DEFAULT_MAIN_SQLITE = Path(r"F:\X9_AI_system\core\database.db")
DEFAULT_X9_SQLITE = Path(r"F:\X9_AI_system\desktop\data\creators.sqlite")

LOCAL_TABLES = [
    "creators",
    "tag_definitions",
    "creator_tags",
    "creator_recommendations",
    "raw_observations",
    "review_tasks",
    "extension_sessions",
    "extension_commands",
    "extension_run_progress",
    "gmail_accounts",
    "outreach_emails",
    "outreach_templates",
]

LOCAL_CONFLICT_KEYS = {
    "creators": ["id"],
    "tag_definitions": ["tag_code"],
    "creator_tags": ["id"],
    "creator_recommendations": ["id"],
    "raw_observations": ["id"],
    "review_tasks": ["id"],
    "extension_sessions": ["id"],
    "extension_commands": ["id"],
    "extension_run_progress": ["id"],
    "gmail_accounts": ["id"],
    "outreach_emails": ["id"],
    "outreach_templates": ["id"],
}


@dataclass
class ColumnInfo:
    cid: int
    name: str
    sqlite_type: str
    not_null: bool
    default: Any
    pk_position: int


def sqlite_ro(path: Path) -> sqlite3.Connection:
    uri = "file:" + path.as_posix() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = None
    return con


def table_names(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows]


def columns_for(con: sqlite3.Connection, table: str) -> list[ColumnInfo]:
    rows = con.execute(f"PRAGMA table_info({quote_sqlite_ident(table)})").fetchall()
    return [
        ColumnInfo(
            cid=row[0],
            name=row[1],
            sqlite_type=row[2] or "",
            not_null=bool(row[3]),
            default=row[4],
            pk_position=int(row[5] or 0),
        )
        for row in rows
    ]


def quote_sqlite_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def pg_type_for(
    con: sqlite3.Connection, table: str, column: ColumnInfo, warnings: list[str]
) -> str:
    declared = column.sqlite_type.upper()
    if table == "_meta_resource" and column.name == "writable":
        return "BIGINT"
    if column.pk_position and declared == "INTEGER":
        return "BIGSERIAL"

    if "INT" in declared:
        if has_type_mismatch(con, table, column.name, {"integer"}):
            warnings.append(
                f"{table}.{column.name}: declared INTEGER but contains non-integer values; using TEXT"
            )
            return "TEXT"
        return "BIGINT"
    if any(token in declared for token in ["REAL", "FLOA", "DOUB"]):
        if has_type_mismatch(con, table, column.name, {"integer", "real"}):
            warnings.append(
                f"{table}.{column.name}: declared REAL but contains non-numeric values; using TEXT"
            )
            return "TEXT"
        return "DOUBLE PRECISION"
    if any(token in declared for token in ["NUM", "DEC"]):
        return "NUMERIC"
    if "BLOB" in declared:
        return "BYTEA"
    return "TEXT"


def has_type_mismatch(
    con: sqlite3.Connection, table: str, column: str, allowed_types: set[str]
) -> bool:
    allowed = ", ".join("'" + t + "'" for t in sorted(allowed_types | {"null"}))
    query = (
        f"SELECT 1 FROM {quote_sqlite_ident(table)} "
        f"WHERE typeof({quote_sqlite_ident(column)}) NOT IN ({allowed}) LIMIT 1"
    )
    return con.execute(query).fetchone() is not None


def create_table_from_sqlite(
    pg_cur: psycopg.Cursor,
    sqlite_con: sqlite3.Connection,
    source_table: str,
    target_table: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    target_table = target_table or source_table
    warnings = warnings if warnings is not None else []
    columns = columns_for(sqlite_con, source_table)
    if not columns:
        return

    column_defs: list[sql.Composable] = []
    for column in columns:
        pg_type = pg_type_for(sqlite_con, source_table, column, warnings)
        column_defs.append(
            sql.SQL("{} {}").format(sql.Identifier(column.name), sql.SQL(pg_type))
        )

    pk_cols = [column.name for column in columns if column.pk_position]
    if pk_cols:
        pk_cols_sorted = [
            column.name for column in sorted(columns, key=lambda c: c.pk_position or 9999) if column.pk_position
        ]
        column_defs.append(
            sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in pk_cols_sorted)
            )
        )

    pg_cur.execute(
        sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
            sql.Identifier(target_table), sql.SQL(", ").join(column_defs)
        )
    )


def import_table(
    pg_cur: psycopg.Cursor,
    sqlite_con: sqlite3.Connection,
    source_table: str,
    target_table: str | None = None,
    batch_size: int = 500,
) -> int:
    target_table = target_table or source_table
    columns = [column.name for column in columns_for(sqlite_con, source_table)]
    if not columns:
        return 0

    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(target_table),
        sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        placeholders,
    )

    total = 0
    sqlite_cur = sqlite_con.execute(f"SELECT * FROM {quote_sqlite_ident(source_table)}")
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        rows = [normalise_source_row(source_table, columns, row) for row in rows]
        pg_cur.executemany(insert_sql, rows)
        total += len(rows)
    return total


def normalise_source_row(table: str, columns: list[str], row: Iterable[Any]) -> tuple[Any, ...]:
    values = list(row)
    if table == "_meta_resource":
        try:
            description_i = columns.index("description")
            writable_i = columns.index("writable")
        except ValueError:
            return tuple(values)
        writable_value = values[writable_i]
        description_value = values[description_i]
        if isinstance(writable_value, str) and not writable_value.strip().isdigit():
            values[description_i] = writable_value
            values[writable_i] = 1 if description_value in (1, "1", True) else description_value
    return tuple(values)


def recreate_indexes(
    pg_cur: psycopg.Cursor,
    sqlite_con: sqlite3.Connection,
    table: str,
    target_table: str | None = None,
    warnings: list[str] | None = None,
) -> int:
    target_table = target_table or table
    warnings = warnings if warnings is not None else []
    created = 0
    for index in sqlite_con.execute(f"PRAGMA index_list({quote_sqlite_ident(table)})"):
        index_name = index[1]
        is_unique = bool(index[2])
        origin = index[3] if len(index) > 3 else ""
        partial = bool(index[4]) if len(index) > 4 else False
        if origin == "pk" or partial or index_name.startswith("sqlite_autoindex"):
            continue

        xinfo = sqlite_con.execute(f"PRAGMA index_xinfo({quote_sqlite_ident(index_name)})").fetchall()
        cols = [row[2] for row in xinfo if row[5] and row[2] is not None]
        if not cols:
            warnings.append(f"{table}.{index_name}: skipped expression index")
            continue

        pg_index_name = safe_index_name(target_table, index_name)
        create = "CREATE UNIQUE INDEX IF NOT EXISTS" if is_unique else "CREATE INDEX IF NOT EXISTS"
        stmt = sql.SQL("{} {} ON {} ({})").format(
            sql.SQL(create),
            sql.Identifier(pg_index_name),
            sql.Identifier(target_table),
            sql.SQL(", ").join(sql.Identifier(col) for col in cols),
        )
        if execute_best_effort(pg_cur, stmt, warnings, f"index {pg_index_name}"):
            created += 1
    return created


def safe_index_name(table: str, index_name: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{table}_{index_name}").strip("_").lower()
    if len(raw) <= 60:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{raw[:51]}_{digest}"


def execute_best_effort(
    pg_cur: psycopg.Cursor,
    stmt: sql.Composable,
    warnings: list[str],
    label: str,
) -> bool:
    pg_cur.execute("SAVEPOINT best_effort")
    try:
        pg_cur.execute(stmt)
    except Exception as exc:  # noqa: BLE001 - we want migration to continue after optional index failures.
        pg_cur.execute("ROLLBACK TO SAVEPOINT best_effort")
        warnings.append(f"{label}: skipped ({exc})")
        return False
    finally:
        pg_cur.execute("RELEASE SAVEPOINT best_effort")
    return True


def table_exists(pg_cur: psycopg.Cursor, table: str) -> bool:
    pg_cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public'
            AND table_name = %s
        )
        """,
        (table,),
    )
    return bool(pg_cur.fetchone()[0])


def target_columns(pg_cur: psycopg.Cursor, table: str) -> list[str]:
    pg_cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in pg_cur.fetchall()]


def count_rows(pg_cur: psycopg.Cursor, table: str) -> int:
    pg_cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
    return int(pg_cur.fetchone()[0])


def upsert_local_table(
    pg_cur: psycopg.Cursor,
    sqlite_con: sqlite3.Connection,
    source_table: str,
    target_table: str | None = None,
    conflict_keys: list[str] | None = None,
    exclude_columns: set[str] | None = None,
    batch_size: int = 500,
) -> dict[str, int | str]:
    target_table = target_table or source_table
    conflict_keys = conflict_keys or LOCAL_CONFLICT_KEYS[source_table]
    exclude_columns = exclude_columns or set()
    source_cols = [column.name for column in columns_for(sqlite_con, source_table)]
    dest_cols = target_columns(pg_cur, target_table)
    columns = [
        column
        for column in source_cols
        if column in dest_cols and column not in exclude_columns
    ]
    missing_conflicts = [column for column in conflict_keys if column not in columns]
    if missing_conflicts:
        raise RuntimeError(
            f"{source_table} -> {target_table}: conflict columns missing: {missing_conflicts}"
        )

    before = count_rows(pg_cur, target_table)
    update_cols = [column for column in columns if column not in conflict_keys]
    insert_stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) ").format(
        sql.Identifier(target_table),
        sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(sql.Identifier(col) for col in conflict_keys),
    )
    if update_cols:
        insert_stmt += sql.SQL("DO UPDATE SET {}").format(
            sql.SQL(", ").join(
                sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(col), sql.Identifier(col))
                for col in update_cols
            )
        )
    else:
        insert_stmt += sql.SQL("DO NOTHING")

    select_cols = ", ".join(quote_sqlite_ident(column) for column in columns)
    sqlite_cur = sqlite_con.execute(
        f"SELECT {select_cols} FROM {quote_sqlite_ident(source_table)}"
    )

    processed = 0
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        pg_cur.executemany(insert_stmt, rows)
        processed += len(rows)

    after = count_rows(pg_cur, target_table)
    return {
        "source": source_table,
        "target": target_table,
        "processed": processed,
        "before": before,
        "after": after,
        "net_new": after - before,
    }


def ensure_unique_index(
    pg_cur: psycopg.Cursor,
    table: str,
    columns: list[str],
    name: str,
    warnings: list[str],
) -> None:
    stmt = sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({})").format(
        sql.Identifier(name),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    execute_best_effort(pg_cur, stmt, warnings, f"unique index {name}")


def ensure_useful_indexes(pg_cur: psycopg.Cursor, warnings: list[str]) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_tk_creators_priority_pg ON tk_creators (outreach_priority, recommendation_score, fit_level, followers_count)",
        "CREATE INDEX IF NOT EXISTS idx_tk_creators_filters_pg ON tk_creators (primary_product_category, has_email, recommendation_status)",
        "CREATE INDEX IF NOT EXISTS idx_tk_creators_status_pg ON tk_creators (current_status, owner_bd)",
        "CREATE INDEX IF NOT EXISTS idx_tk_creators_collected_pg ON tk_creators (collected_at)",
        "CREATE INDEX IF NOT EXISTS idx_creators_handle_pg ON creators (platform, handle)",
        "CREATE INDEX IF NOT EXISTS idx_creator_tags_lookup_pg ON creator_tags (creator_id, tag_code)",
        "CREATE INDEX IF NOT EXISTS idx_raw_observations_hash_pg ON raw_observations (content_hash)",
        "CREATE INDEX IF NOT EXISTS idx_recommendations_creator_pg ON creator_recommendations (creator_id)",
        "CREATE INDEX IF NOT EXISTS idx_outreach_emails_creator_pg ON outreach_emails (creator_id)",
        "CREATE INDEX IF NOT EXISTS idx_outreach_emails_status_pg ON outreach_emails (status, created_at)",
    ]
    for statement in statements:
        execute_best_effort(pg_cur, sql.SQL(statement), warnings, statement.split()[5])


def clean_new_database_copy(pg_cur: psycopg.Cursor) -> dict[str, int]:
    cleanup: dict[str, int] = {}
    deletes = {
        "api_key_orphans_removed": """
            WITH deleted AS (
              DELETE FROM api_key k
              WHERE NOT EXISTS (SELECT 1 FROM api_user u WHERE u.id = k.user_id)
              RETURNING 1
            )
            SELECT COUNT(*) FROM deleted
        """,
        "keyword_snapshot_orphans_removed": """
            WITH deleted AS (
              DELETE FROM keyword_snapshot s
              WHERE NOT EXISTS (SELECT 1 FROM tk_hot_keyword k WHERE k.id = s.keyword_id)
              RETURNING 1
            )
            SELECT COUNT(*) FROM deleted
        """,
    }
    for key, statement in deletes.items():
        if key.startswith("api_key") and not table_exists(pg_cur, "api_key"):
            cleanup[key] = 0
            continue
        if key.startswith("keyword_snapshot") and not table_exists(pg_cur, "keyword_snapshot"):
            cleanup[key] = 0
            continue
        pg_cur.execute(statement)
        cleanup[key] = int(pg_cur.fetchone()[0])
    return cleanup


def reset_public_schema(pg_cur: psycopg.Cursor) -> None:
    pg_cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
    pg_cur.execute("CREATE SCHEMA public")
    pg_cur.execute("GRANT ALL ON SCHEMA public TO x9")
    pg_cur.execute("GRANT ALL ON SCHEMA public TO public")


def set_sequences(pg_cur: psycopg.Cursor, tables: Iterable[str]) -> None:
    for table in tables:
        if "id" not in target_columns(pg_cur, table):
            continue
        pg_cur.execute("SELECT pg_get_serial_sequence(%s, %s)", (f"public.{table}", "id"))
        sequence = pg_cur.fetchone()[0]
        if not sequence:
            continue
        pg_cur.execute(
            sql.SQL(
                """
                SELECT setval(
                  %s::regclass,
                  COALESCE((SELECT MAX(id) FROM {}), 1),
                  (SELECT MAX(id) FROM {}) IS NOT NULL
                )
                """
            ).format(sql.Identifier(table), sql.Identifier(table)),
            (sequence,),
        )


def create_migration_manifest(pg_cur: psycopg.Cursor, summary: dict[str, Any]) -> None:
    pg_cur.execute(
        """
        CREATE TABLE IF NOT EXISTS migration_manifest (
          id BIGSERIAL PRIMARY KEY,
          created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
          summary_json JSONB NOT NULL
        )
        """
    )
    pg_cur.execute(
        "INSERT INTO migration_manifest (summary_json) VALUES (%s)",
        (json.dumps(summary, ensure_ascii=False),),
    )


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    main_sqlite = Path(args.main_sqlite)
    x9_sqlite = Path(args.x9_sqlite)
    if not main_sqlite.exists():
        raise FileNotFoundError(main_sqlite)
    if not x9_sqlite.exists():
        raise FileNotFoundError(x9_sqlite)

    with sqlite_ro(main_sqlite) as main_con, sqlite_ro(x9_sqlite) as x9_con, psycopg.connect(
        args.pg_dsn
    ) as pg_con:
        with pg_con.cursor() as pg_cur:
            if args.reset_target:
                reset_public_schema(pg_cur)

            imported: dict[str, int] = {}
            main_tables = table_names(main_con)
            for table in main_tables:
                create_table_from_sqlite(pg_cur, main_con, table, warnings=warnings)
            for table in main_tables:
                imported[table] = import_table(pg_cur, main_con, table)

            recreated_indexes = 0
            for table in main_tables:
                recreated_indexes += recreate_indexes(pg_cur, main_con, table, warnings=warnings)

            local_results = []
            for table in LOCAL_TABLES:
                if table not in table_names(x9_con):
                    warnings.append(f"local table {table}: not found")
                    continue
                if not table_exists(pg_cur, table):
                    create_table_from_sqlite(pg_cur, x9_con, table, warnings=warnings)
                    recreate_indexes(pg_cur, x9_con, table, warnings=warnings)
                local_results.append(
                    upsert_local_table(
                        pg_cur,
                        x9_con,
                        table,
                        conflict_keys=LOCAL_CONFLICT_KEYS[table],
                    )
                )

            ensure_unique_index(
                pg_cur,
                "tk_creators",
                ["platform", "handle"],
                "uq_tk_creators_platform_handle_pg",
                warnings,
            )
            local_results.append(
                upsert_local_table(
                    pg_cur,
                    x9_con,
                    "creators",
                    target_table="tk_creators",
                    conflict_keys=["platform", "handle"],
                    exclude_columns={"id"},
                )
            )

            ensure_useful_indexes(pg_cur, warnings)
            cleanup = clean_new_database_copy(pg_cur)
            set_sequences(pg_cur, table_names(main_con) + ["migration_manifest"])

            summary: dict[str, Any] = {
                "main_sqlite": str(main_sqlite),
                "x9_sqlite": str(x9_sqlite),
                "main_tables": len(main_tables),
                "main_imported_rows": imported,
                "sqlite_indexes_recreated": recreated_indexes,
                "local_merge": local_results,
                "cleanup": cleanup,
                "warnings": warnings,
            }
            create_migration_manifest(pg_cur, summary)
            return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate the current SQLite databases into the local PostgreSQL database."
    )
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--main-sqlite", default=str(DEFAULT_MAIN_SQLITE))
    parser.add_argument("--x9-sqlite", default=str(DEFAULT_X9_SQLITE))
    parser.add_argument(
        "--reset-target",
        action="store_true",
        help="Drop and recreate only the PostgreSQL public schema before importing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = migrate(parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
