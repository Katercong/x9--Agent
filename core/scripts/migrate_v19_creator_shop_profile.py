"""migrate_v19: store TikTok Shop creator profile/performance page data.

This migration is intentionally storage-only. It does not change the scoring,
tagging, or recommendation model.

It adds:
  - creator_shop_snapshots: one row per captured creator page/performance window
  - creator_shop_category_distribution: GMV category split per snapshot
  - creator_shop_example_videos: representative shoppable videos per snapshot
  - creator_shop_similar_creators: similar creator cards per snapshot

It also adds a small set of nullable "latest shop_*" columns to creator tables
when they exist, so list pages can filter common fields without joining the
snapshot tables.

Usage:
  py core/scripts/migrate_v19_creator_shop_profile.py
  py core/scripts/migrate_v19_creator_shop_profile.py --sqlite core/database.db
  py core/scripts/migrate_v19_creator_shop_profile.py --pg-dsn postgresql://...
  py core/scripts/migrate_v19_creator_shop_profile.py --both
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Protocol

import psycopg
from psycopg import sql


DEFAULT_SQLITE = Path(__file__).resolve().parent.parent / "database.db"
DEFAULT_PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)


class Runner(Protocol):
    dialect: str

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        ...

    def fetchall(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        ...

    def table_exists(self, table: str) -> bool:
        ...

    def column_exists(self, table: str, column: str) -> bool:
        ...

    def add_column(self, table: str, column: str, column_type: str) -> None:
        ...


class SQLiteRunner:
    dialect = "sqlite"

    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        self.con.execute(statement, params)

    def fetchall(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        return self.con.execute(statement, params).fetchall()

    def table_exists(self, table: str) -> bool:
        row = self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None

    def column_exists(self, table: str, column: str) -> bool:
        return any(row[1] == column for row in self.con.execute(f"PRAGMA table_info({q(table)})"))

    def add_column(self, table: str, column: str, column_type: str) -> None:
        if not self.column_exists(table, column):
            self.con.execute(f"ALTER TABLE {q(table)} ADD COLUMN {q(column)} {column_type}")


class PostgresRunner:
    dialect = "postgresql"

    def __init__(self, con: psycopg.Connection) -> None:
        self.con = con

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        with self.con.cursor() as cur:
            cur.execute(statement, params)

    def fetchall(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.con.cursor() as cur:
            cur.execute(statement, params)
            return cur.fetchall()

    def table_exists(self, table: str) -> bool:
        rows = self.fetchall(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table,),
        )
        return bool(rows)

    def column_exists(self, table: str, column: str) -> bool:
        rows = self.fetchall(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            """,
            (table, column),
        )
        return bool(rows)

    def add_column(self, table: str, column: str, column_type: str) -> None:
        with self.con.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} ").format(
                    sql.Identifier(table),
                    sql.Identifier(column),
                )
                + sql.SQL(column_type)
            )


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


LATEST_COLUMNS: list[tuple[str, str]] = [
    ("shop_account_handle", "TEXT"),
    ("shop_rating", "TEXT"),
    ("shop_main_category", "TEXT"),
    ("shop_additional_categories_count", "INTEGER"),
    ("shop_location_or_identity_text", "TEXT"),
    ("shop_instagram_handle", "TEXT"),
    ("shop_external_link", "TEXT"),
    ("shop_flat_fee_eligibility", "TEXT"),
    ("shop_invite_status", "TEXT"),
    ("shop_pps_score", "NUMERIC"),
    ("shop_pps_level", "TEXT"),
    ("shop_sample_score", "INTEGER"),
    ("shop_sample_level", "TEXT"),
    ("shop_gmv_range", "TEXT"),
    ("shop_items_sold_range", "TEXT"),
    ("shop_gpm_range", "TEXT"),
    ("shop_gmv_per_customer_range", "TEXT"),
    ("shop_estimated_post_rate", "TEXT"),
    ("shop_average_commission_rate", "TEXT"),
    ("shop_videos_count", "INTEGER"),
    ("shop_average_video_views", "TEXT"),
    ("shop_average_video_engagement_rate", "TEXT"),
    ("shop_live_streams_count", "INTEGER"),
    ("shop_average_live_views", "TEXT"),
    ("shop_average_live_engagement_rate", "TEXT"),
    ("shop_latest_snapshot_id", "TEXT"),
    ("shop_latest_snapshot_at", "TIMESTAMP"),
]


META_RESOURCES = [
    (
        "creator_shop_snapshots",
        "creator_shop_snapshots",
        "id",
        ["id"],
        [
            "gmv_per_sales_channel_json",
            "products_json",
            "brand_collaborations_json",
            "audience_profile_json",
            "trend_metrics_json",
            "main_strengths_json",
            "main_weaknesses_json",
            "recommended_cooperation_type_json",
            "raw_json",
        ],
        "Captured TikTok Shop creator profile and performance snapshot.",
    ),
    (
        "creator_shop_category_distribution",
        "creator_shop_category_distribution",
        "id",
        ["snapshot_id", "category"],
        [],
        "GMV category distribution for a creator shop snapshot.",
    ),
    (
        "creator_shop_example_videos",
        "creator_shop_example_videos",
        "id",
        ["snapshot_id", "caption_or_title", "publish_date"],
        [],
        "Representative shoppable videos from a creator shop snapshot.",
    ),
    (
        "creator_shop_similar_creators",
        "creator_shop_similar_creators",
        "id",
        ["snapshot_id", "account_handle"],
        [],
        "Similar creator cards captured with a creator shop snapshot.",
    ),
]


def create_tables(r: Runner) -> None:
    id_col = "BIGSERIAL PRIMARY KEY" if r.dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    snapshot_fk_col = "BIGINT" if r.dialect == "postgresql" else "INTEGER"
    now_expr = "CURRENT_TIMESTAMP" if r.dialect == "postgresql" else "(datetime('now'))"

    r.execute(
        f"""
        CREATE TABLE IF NOT EXISTS creator_shop_snapshots (
            id                                      {id_col},
            creator_source_table                    TEXT DEFAULT 'tk_creators',
            creator_id                              TEXT,
            platform                                TEXT DEFAULT 'tiktok',
            handle                                  TEXT NOT NULL,
            account_handle                          TEXT,
            display_name                            TEXT,
            rating                                  TEXT,
            main_category                           TEXT,
            additional_categories_count             INTEGER,
            followers_raw                           TEXT,
            bio                                     TEXT,
            location_or_identity_text               TEXT,
            email                                   TEXT,
            instagram_handle                        TEXT,
            external_link                           TEXT,
            flat_fee_eligibility                    TEXT,
            invite_status                           TEXT,

            pps_score                               NUMERIC,
            pps_max_score                           NUMERIC,
            pps_level                               TEXT,
            pps_description                         TEXT,

            metric_start_date                       TEXT,
            metric_end_date                         TEXT,
            metric_timezone                         TEXT,

            sample_score_total                      INTEGER,
            sample_score_max                        INTEGER,
            sample_score_level                      TEXT,
            posts_with_samples_score                INTEGER,
            posts_with_samples_level                TEXT,
            posts_with_samples_comparison           TEXT,
            post_frequency_score                    INTEGER,
            post_frequency_level                    TEXT,
            post_frequency_comparison               TEXT,
            sales_generation_score                  INTEGER,
            sales_generation_level                  TEXT,
            sales_generation_comparison             TEXT,
            content_quality_score                   INTEGER,
            content_quality_level                   TEXT,
            content_quality_comparison              TEXT,

            gmv_range                               TEXT,
            items_sold_range                        TEXT,
            gpm_range                               TEXT,
            gmv_per_customer_range                  TEXT,
            gmv_per_sales_channel_json              TEXT,

            estimated_post_rate                     TEXT,
            average_commission_rate                 TEXT,
            products_json                           TEXT,
            brand_collaborations_json               TEXT,

            video_gpm_range                         TEXT,
            videos_count                            INTEGER,
            average_video_views                     TEXT,
            average_video_engagement_rate           TEXT,
            live_gpm_range                          TEXT,
            live_streams_count                      INTEGER,
            average_live_views                      TEXT,
            average_live_engagement_rate            TEXT,

            audience_profile_json                   TEXT,
            trend_metrics_json                      TEXT,

            creator_type                            TEXT,
            main_strengths_json                     TEXT,
            main_weaknesses_json                    TEXT,
            recommended_cooperation_type_json       TEXT,
            risk_level                              TEXT,
            priority_level                          TEXT,

            source                                  TEXT DEFAULT 'creator_page_text',
            raw_json                                TEXT,
            captured_at                             TIMESTAMP NOT NULL DEFAULT {now_expr},
            created_at                              TIMESTAMP NOT NULL DEFAULT {now_expr},
            updated_at                              TIMESTAMP NOT NULL DEFAULT {now_expr}
        )
        """
    )
    r.execute(
        f"""
        CREATE TABLE IF NOT EXISTS creator_shop_category_distribution (
            id             {id_col},
            snapshot_id    {snapshot_fk_col} NOT NULL REFERENCES creator_shop_snapshots(id) ON DELETE CASCADE,
            category       TEXT NOT NULL,
            percentage     NUMERIC,
            created_at     TIMESTAMP NOT NULL DEFAULT {now_expr},
            UNIQUE(snapshot_id, category)
        )
        """
    )
    r.execute(
        f"""
        CREATE TABLE IF NOT EXISTS creator_shop_example_videos (
            id                         {id_col},
            snapshot_id                {snapshot_fk_col} NOT NULL REFERENCES creator_shop_snapshots(id) ON DELETE CASCADE,
            creator_id                 TEXT,
            platform                   TEXT DEFAULT 'tiktok',
            handle                     TEXT,
            caption_or_title           TEXT,
            publish_date               TEXT,
            views_raw                  TEXT,
            views_count                INTEGER,
            engagement_or_likes_raw    TEXT,
            engagement_or_likes_count  INTEGER,
            has_product_link           INTEGER DEFAULT 0,
            action_available           TEXT,
            video_url                  TEXT,
            created_at                 TIMESTAMP NOT NULL DEFAULT {now_expr},
            UNIQUE(snapshot_id, caption_or_title, publish_date)
        )
        """
    )
    r.execute(
        f"""
        CREATE TABLE IF NOT EXISTS creator_shop_similar_creators (
            id                     {id_col},
            snapshot_id            {snapshot_fk_col} NOT NULL REFERENCES creator_shop_snapshots(id) ON DELETE CASCADE,
            account_handle         TEXT NOT NULL,
            tag                    TEXT,
            pps_score              NUMERIC,
            pps_max_score          NUMERIC,
            category               TEXT,
            followers_raw          TEXT,
            followers_count        INTEGER,
            gmv_raw                TEXT,
            gmv_usd                NUMERIC,
            items_sold_raw         TEXT,
            items_sold_count       INTEGER,
            average_views_raw      TEXT,
            average_views_count    INTEGER,
            created_at             TIMESTAMP NOT NULL DEFAULT {now_expr},
            UNIQUE(snapshot_id, account_handle)
        )
        """
    )


def create_indexes(r: Runner) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_creator ON creator_shop_snapshots (creator_source_table, creator_id)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_handle ON creator_shop_snapshots (platform, handle)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_captured ON creator_shop_snapshots (captured_at)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_category ON creator_shop_snapshots (main_category)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_pps ON creator_shop_snapshots (pps_score)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_sample ON creator_shop_snapshots (sample_score_total)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_snapshots_window ON creator_shop_snapshots (metric_start_date, metric_end_date)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_dist_snapshot ON creator_shop_category_distribution (snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_dist_category ON creator_shop_category_distribution (category)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_videos_snapshot ON creator_shop_example_videos (snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_videos_handle ON creator_shop_example_videos (platform, handle)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_videos_publish ON creator_shop_example_videos (publish_date)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_similar_snapshot ON creator_shop_similar_creators (snapshot_id)",
        "CREATE INDEX IF NOT EXISTS ix_creator_shop_similar_handle ON creator_shop_similar_creators (account_handle)",
    ]
    for statement in statements:
        r.execute(statement)


def add_latest_columns(r: Runner) -> list[str]:
    touched: list[str] = []
    for table in ("tk_creators", "creators", "creator"):
        if not r.table_exists(table):
            continue
        for column, column_type in LATEST_COLUMNS:
            r.add_column(table, column, column_type)
        touched.append(table)
        r.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_shop_main_category ON {q(table)} (shop_main_category)")
        r.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_shop_pps_score ON {q(table)} (shop_pps_score)")
        r.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_shop_sample_score ON {q(table)} (shop_sample_score)")
        r.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_shop_latest_snapshot_at ON {q(table)} (shop_latest_snapshot_at)")
    return touched


def register_resources(r: Runner) -> int:
    if not r.table_exists("_meta_resource"):
        return 0
    if r.dialect == "postgresql":
        stmt = """
            INSERT INTO _meta_resource(
                name, table_name, pk, upsert_keys, json_cols, fk_lookup,
                description, is_dynamic, writable
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1)
            ON CONFLICT (name) DO UPDATE SET
                table_name = EXCLUDED.table_name,
                pk = EXCLUDED.pk,
                upsert_keys = EXCLUDED.upsert_keys,
                json_cols = EXCLUDED.json_cols,
                fk_lookup = EXCLUDED.fk_lookup,
                description = EXCLUDED.description,
                is_dynamic = EXCLUDED.is_dynamic,
                writable = EXCLUDED.writable
        """
    else:
        stmt = """
            INSERT INTO _meta_resource(
                name, table_name, pk, upsert_keys, json_cols, fk_lookup,
                description, is_dynamic, writable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1)
            ON CONFLICT(name) DO UPDATE SET
                table_name = excluded.table_name,
                pk = excluded.pk,
                upsert_keys = excluded.upsert_keys,
                json_cols = excluded.json_cols,
                fk_lookup = excluded.fk_lookup,
                description = excluded.description,
                is_dynamic = excluded.is_dynamic,
                writable = excluded.writable
        """
    for name, table, pk, upsert_keys, json_cols, desc in META_RESOURCES:
        r.execute(
            stmt,
            (
                name,
                table,
                pk,
                json.dumps(upsert_keys),
                json.dumps(json_cols),
                json.dumps({}),
                desc,
            ),
        )
    return len(META_RESOURCES)


def migrate_runner(r: Runner) -> dict[str, Any]:
    create_tables(r)
    create_indexes(r)
    touched = add_latest_columns(r)
    registered = register_resources(r)
    return {
        "dialect": r.dialect,
        "latest_columns_added_to": touched,
        "resources_registered": registered,
    }


def migrate_sqlite(path: Path) -> dict[str, Any]:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        result = migrate_runner(SQLiteRunner(con))
        con.commit()
        result["database"] = str(path)
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def migrate_postgres(dsn: str) -> dict[str, Any]:
    with psycopg.connect(dsn) as con:
        try:
            result = migrate_runner(PostgresRunner(con))
            con.commit()
            result["database"] = dsn.split("@")[-1] if "@" in dsn else dsn
            return result
        except Exception:
            con.rollback()
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="SQLite database path.")
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN, help="PostgreSQL DSN.")
    parser.add_argument("--postgres", action="store_true", help="Run only against PostgreSQL.")
    parser.add_argument("--both", action="store_true", help="Run against SQLite and PostgreSQL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results: list[dict[str, Any]] = []
    if args.postgres:
        results.append(migrate_postgres(args.pg_dsn))
    elif args.both:
        results.append(migrate_sqlite(Path(args.sqlite)))
        results.append(migrate_postgres(args.pg_dsn))
    else:
        results.append(migrate_sqlite(Path(args.sqlite)))
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
