"""migrate_v20: make the React admin /api/v1 surface complete on PostgreSQL.

This migration is PostgreSQL-only and idempotent. It adds the UI support
tables that existed only in SQLite, registers them in _meta_resource, and
rewrites built-in _meta_query SQL to PostgreSQL syntax.

Usage:
  py core/scripts/migrate_v20_api_v1_postgres_ui.py
  py core/scripts/migrate_v20_api_v1_postgres_ui.py --pg-dsn postgresql://...
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PG_DSN_FALLBACK = "postgresql://x9:x9_local_dev_2026@127.0.0.1:15432/x9db?connect_timeout=5"


def load_shared_env() -> None:
    env_path = ROOT / ".env.shared"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_shared_env()
DEFAULT_PG_DSN = os.environ.get("X9_PG_DSN", DEFAULT_PG_DSN_FALLBACK)


def table_exists(cur: psycopg.Cursor, table: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table,),
    )
    return bool(cur.fetchone()[0])


def column_exists(cur: psycopg.Cursor, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = %s
            AND column_name = %s
        )
        """,
        (table, column),
    )
    return bool(cur.fetchone()[0])


def add_department_id(cur: psycopg.Cursor, table: str, results: list[tuple[str, str]]) -> None:
    if not table_exists(cur, table):
        results.append((f"{table}.department_id", "table missing, skipped"))
        return
    if not column_exists(cur, table, "department_id"):
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN department_id BIGINT REFERENCES department(id)").format(
                sql.Identifier(table)
            )
        )
        results.append((f"{table}.department_id", "added"))
    else:
        results.append((f"{table}.department_id", "exists"))
    cur.execute(
        sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} (department_id)").format(
            sql.Identifier(f"idx_{table}_department_id"),
            sql.Identifier(table),
        )
    )


def register_resource(
    cur: psycopg.Cursor,
    *,
    name: str,
    table_name: str,
    description: str,
    writable: bool,
) -> None:
    payload = (
        name,
        table_name,
        "id",
        "[]",
        "[]",
        "{}",
        description,
        1,
        1 if writable else 0,
    )
    cur.execute(
        """
        INSERT INTO _meta_resource(
          name, table_name, pk, upsert_keys, json_cols, fk_lookup,
          description, is_dynamic, writable
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (name) DO UPDATE SET
          table_name = EXCLUDED.table_name,
          pk = EXCLUDED.pk,
          upsert_keys = EXCLUDED.upsert_keys,
          json_cols = EXCLUDED.json_cols,
          fk_lookup = EXCLUDED.fk_lookup,
          description = EXCLUDED.description,
          is_dynamic = EXCLUDED.is_dynamic,
          writable = EXCLUDED.writable
        """,
        payload,
    )


PG_QUERIES: dict[str, tuple[str, str, list[tuple[str, str, Any]]]] = {
    "creators_to_contact": (
        "Creators waiting for first outreach.",
        """
        SELECT id, handle, platform, profile_url, email, created_at, followers, tier,
               avg_views, gmv_30d_usd, pps, category_tags, country, source, department_id
        FROM creator
        WHERE current_status = 'prospect'
          AND (%(department_id)s::bigint IS NULL OR department_id = %(department_id)s::bigint)
          AND (%(category)s::text IS NULL OR POSITION(LOWER(%(category)s::text) IN LOWER(COALESCE(category_tags, ''))) > 0)
          AND (%(min_followers)s::bigint IS NULL OR followers >= %(min_followers)s::bigint)
        ORDER BY followers DESC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("category", "str", None), ("min_followers", "int", None), ("limit", "int", 50)],
    ),
    "creators_follow_up": (
        "Creators contacted but quiet for N days.",
        """
        SELECT id, handle, platform, profile_url, current_status, last_contact_date,
               owner_bd, store_assigned, department_id
        FROM creator
        WHERE current_status IN ('contacted','confirmed','sample_shipped','sample_delivered')
          AND (%(department_id)s::bigint IS NULL OR department_id = %(department_id)s::bigint)
          AND COALESCE(NULLIF(last_contact_date, ''), '0001-01-01')
              < to_char(CURRENT_DATE - (%(stale_days)s::bigint * INTERVAL '1 day'), 'YYYY-MM-DD')
        ORDER BY last_contact_date ASC NULLS FIRST
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("stale_days", "int", 2), ("limit", "int", 100)],
    ),
    "outreach_video_tracking": (
        "Published videos whose metrics are stale.",
        """
        SELECT o.id AS outreach_id, c.handle, c.platform, o.video_url,
               o.video_views, o.video_likes, o.video_comments, o.video_shares,
               o.metrics_updated_at, o.event_date, o.department_id
        FROM outreach o
        JOIN creator c ON c.id = o.creator_id
        WHERE o.video_url IS NOT NULL AND o.video_url <> ''
          AND (%(department_id)s::bigint IS NULL OR o.department_id = %(department_id)s::bigint)
          AND (
            o.metrics_updated_at IS NULL OR o.metrics_updated_at = ''
            OR o.metrics_updated_at < to_char(NOW() - (%(stale_hours)s::bigint * INTERVAL '1 hour'), 'YYYY-MM-DD HH24:MI:SS')
          )
        ORDER BY COALESCE(o.metrics_updated_at, '') ASC
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("stale_hours", "int", 24), ("limit", "int", 100)],
    ),
    "outreach_auth_pending": (
        "Published videos missing Spark Ads auth code.",
        """
        SELECT o.id AS outreach_id, c.handle, c.platform, c.owner_bd,
               o.event_date, o.video_url, o.remark, o.department_id
        FROM outreach o
        JOIN creator c ON c.id = o.creator_id
        WHERE o.video_url IS NOT NULL AND o.video_url <> ''
          AND (%(department_id)s::bigint IS NULL OR o.department_id = %(department_id)s::bigint)
          AND (o.ad_auth_code IS NULL OR o.ad_auth_code = '')
        ORDER BY o.event_date ASC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("limit", "int", 100)],
    ),
    "products_main_push": (
        "Main-push SKU list.",
        """
        SELECT p.id, p.sku_code, p.name_en, p.name_zh, p.tier, p.positioning_zh,
               p.price_tiktok, p.creator_match_levels, c.code AS category_code,
               c.name_zh AS category_name
        FROM product p
        LEFT JOIN category c ON c.id = p.category_id
        WHERE COALESCE(p.is_main_push, 0) = 1
        ORDER BY p.tier NULLS LAST, p.id
        LIMIT %(limit)s::bigint
        """,
        [("limit", "int", 50)],
    ),
    "creators_by_tier": (
        "Creators filtered by tier.",
        """
        SELECT id, handle, platform, profile_url, followers, tier, avg_views,
               gmv_30d_usd, pps, current_status, owner_bd, department_id
        FROM creator
        WHERE tier = %(tier)s::text
          AND (%(department_id)s::bigint IS NULL OR department_id = %(department_id)s::bigint)
        ORDER BY followers DESC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("tier", "str", "A"), ("limit", "int", 100)],
    ),
    "creators_mid_tier_koc": (
        "Mid-tier KOC candidates without competitor collaboration.",
        """
        SELECT c.id, c.handle, c.platform, c.profile_url, c.followers, c.tier,
               c.avg_views, c.engagement_rate, c.gmv_30d_usd, c.pps,
               c.country, c.category_tags, c.current_status, c.owner_bd, c.department_id
        FROM creator c
        WHERE c.followers BETWEEN %(min_followers)s::bigint AND %(max_followers)s::bigint
          AND (%(department_id)s::bigint IS NULL OR c.department_id = %(department_id)s::bigint)
          AND COALESCE(c.excluded, 0) = 0
          AND c.id NOT IN (
            SELECT DISTINCT creator_id
            FROM creator_competitor_collab
            WHERE creator_id IS NOT NULL
          )
          AND (%(category)s::text IS NULL OR POSITION(LOWER(%(category)s::text) IN LOWER(COALESCE(c.category_tags, ''))) > 0)
          AND (%(min_engagement)s::double precision IS NULL OR c.engagement_rate >= %(min_engagement)s::double precision)
          AND (%(country)s::text IS NULL OR c.country = %(country)s::text)
        ORDER BY c.engagement_rate DESC NULLS LAST, c.followers DESC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [
            ("department_id", "int", None),
            ("min_followers", "int", 1000),
            ("max_followers", "int", 500000),
            ("category", "str", None),
            ("min_engagement", "float", None),
            ("country", "str", None),
            ("limit", "int", 100),
        ],
    ),
    "creators_high_engagement": (
        "Creators ordered by engagement rate.",
        """
        SELECT c.id, c.handle, c.followers, c.tier, c.engagement_rate,
               c.avg_views, c.country, c.current_status,
               c.department_id,
               (SELECT COUNT(*)::int FROM creator_competitor_collab WHERE creator_id = c.id) AS competitor_collabs
        FROM creator c
        WHERE COALESCE(c.excluded, 0) = 0
          AND (%(department_id)s::bigint IS NULL OR c.department_id = %(department_id)s::bigint)
          AND c.engagement_rate IS NOT NULL
          AND c.engagement_rate >= %(min_engagement)s::double precision
          AND (%(max_followers)s::bigint IS NULL OR c.followers <= %(max_followers)s::bigint)
        ORDER BY c.engagement_rate DESC
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("min_engagement", "float", 0.03), ("max_followers", "int", None), ("limit", "int", 100)],
    ),
    "creators_blacklisted": (
        "Excluded creators or creators with competitor collaborations.",
        """
        SELECT c.id, c.handle, c.tier, c.followers, c.excluded, c.excluded_reason,
               c.current_status, c.department_id,
               (
                 SELECT STRING_AGG(cb.display_name, '; ' ORDER BY cb.display_name)
                 FROM creator_competitor_collab ccc
                 JOIN competitor_brand cb ON cb.id = ccc.competitor_brand_id
                 WHERE ccc.creator_id = c.id
               ) AS competitor_brands
        FROM creator c
        WHERE (%(department_id)s::bigint IS NULL OR c.department_id = %(department_id)s::bigint)
          AND (
            COALESCE(c.excluded, 0) = 1
            OR c.id IN (
             SELECT DISTINCT creator_id
             FROM creator_competitor_collab
             WHERE creator_id IS NOT NULL
            )
          )
        ORDER BY c.id
        LIMIT %(limit)s::bigint
        """,
        [("department_id", "int", None), ("limit", "int", 200)],
    ),
    "creators_by_content_match": (
        "Creators whose content tags match a product category keyword.",
        """
        SELECT c.id, c.handle, c.tier, c.followers, c.engagement_rate,
               c.category_tags, c.country, c.current_status, c.department_id
        FROM creator c
        WHERE COALESCE(c.excluded, 0) = 0
          AND (%(department_id)s::bigint IS NULL OR c.department_id = %(department_id)s::bigint)
          AND POSITION(LOWER(%(category_keyword)s::text) IN LOWER(COALESCE(c.category_tags, ''))) > 0
          AND (%(min_followers)s::bigint IS NULL OR c.followers >= %(min_followers)s::bigint)
          AND (%(max_followers)s::bigint IS NULL OR c.followers <= %(max_followers)s::bigint)
          AND c.id NOT IN (
            SELECT DISTINCT creator_id
            FROM creator_competitor_collab
            WHERE creator_id IS NOT NULL
          )
        ORDER BY c.engagement_rate DESC NULLS LAST, c.followers DESC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [
            ("department_id", "int", None),
            ("category_keyword", "str", "female_care"),
            ("min_followers", "int", None),
            ("max_followers", "int", None),
            ("limit", "int", 100),
        ],
    ),
    "hot_keywords_recent": (
        "Recent TikTok hot keywords.",
        """
        SELECT id, keyword, source_platform, region, category_hint,
               search_volume, growth_rate, rank_position, last_seen_at
        FROM tk_hot_keyword
        WHERE COALESCE(is_active, 1) = 1
          AND last_seen_at >= to_char(CURRENT_DATE - (%(stale_days)s::bigint * INTERVAL '1 day'), 'YYYY-MM-DD')
          AND (%(platform)s::text IS NULL OR source_platform = %(platform)s::text)
          AND (%(region)s::text IS NULL OR region = %(region)s::text)
        ORDER BY search_volume DESC NULLS LAST, growth_rate DESC NULLS LAST
        LIMIT %(limit)s::bigint
        """,
        [("stale_days", "int", 30), ("platform", "str", "tiktok"), ("region", "str", "US"), ("limit", "int", 50)],
    ),
    "hot_keywords_by_category": (
        "TikTok hot keywords by category.",
        """
        SELECT id, keyword, search_volume, growth_rate, rank_position, last_seen_at
        FROM tk_hot_keyword
        WHERE COALESCE(is_active, 1) = 1
          AND category_hint = %(category)s::text
          AND last_seen_at >= to_char(CURRENT_DATE - (%(stale_days)s::bigint * INTERVAL '1 day'), 'YYYY-MM-DD')
          AND (%(platform)s::text IS NULL OR source_platform = %(platform)s::text)
          AND (%(region)s::text IS NULL OR region = %(region)s::text)
        ORDER BY (COALESCE(search_volume, 0) * (1 + COALESCE(growth_rate, 0))) DESC
        LIMIT %(limit)s::bigint
        """,
        [("category", "str", "female_care"), ("stale_days", "int", 30), ("platform", "str", "tiktok"), ("region", "str", "US"), ("limit", "int", 20)],
    ),
    "hot_keywords_growing": (
        "Fast-growing TikTok hot keywords.",
        """
        SELECT id, keyword, category_hint, source_platform, region,
               search_volume, growth_rate, rank_position, last_seen_at
        FROM tk_hot_keyword
        WHERE COALESCE(is_active, 1) = 1
          AND growth_rate IS NOT NULL
          AND growth_rate >= %(min_growth)s::double precision
          AND last_seen_at >= to_char(CURRENT_DATE - (%(stale_days)s::bigint * INTERVAL '1 day'), 'YYYY-MM-DD')
          AND (%(category)s::text IS NULL OR category_hint = %(category)s::text)
        ORDER BY growth_rate DESC
        LIMIT %(limit)s::bigint
        """,
        [("min_growth", "float", 0.20), ("stale_days", "int", 14), ("category", "str", None), ("limit", "int", 30)],
    ),
}


def upsert_pg_queries(cur: psycopg.Cursor) -> None:
    for name, (description, query_sql, params) in PG_QUERIES.items():
        cur.execute(
            """
            INSERT INTO _meta_query(name, description, sql, params, is_builtin, updated_at)
            VALUES (%s, %s, %s, %s, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
              description = EXCLUDED.description,
              sql = EXCLUDED.sql,
              params = EXCLUDED.params,
              is_builtin = EXCLUDED.is_builtin,
              updated_at = CURRENT_TIMESTAMP
            """,
            (name, description, query_sql.strip(), json.dumps(params, ensure_ascii=False)),
        )


def migrate(dsn: str) -> dict[str, Any]:
    results: list[tuple[str, str]] = []
    with psycopg.connect(dsn) as con:
        with con.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS _meta_resource (
                  name TEXT PRIMARY KEY,
                  table_name TEXT NOT NULL,
                  pk TEXT DEFAULT 'id',
                  upsert_keys TEXT,
                  json_cols TEXT,
                  fk_lookup TEXT,
                  description TEXT,
                  is_dynamic BIGINT NOT NULL DEFAULT 1,
                  writable BIGINT NOT NULL DEFAULT 1,
                  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("ALTER TABLE _meta_resource ADD COLUMN IF NOT EXISTS deprecated_note TEXT")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS _meta_query (
                  name TEXT PRIMARY KEY,
                  description TEXT,
                  sql TEXT NOT NULL,
                  params TEXT,
                  is_builtin BIGINT NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            results.append(("metadata", "_meta_resource/_meta_query ready"))

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS department (
                  id BIGSERIAL PRIMARY KEY,
                  code TEXT UNIQUE NOT NULL,
                  name_zh TEXT NOT NULL,
                  name_en TEXT,
                  parent_id BIGINT REFERENCES department(id),
                  manager TEXT,
                  description TEXT,
                  active BIGINT NOT NULL DEFAULT 1,
                  sort_order BIGINT DEFAULT 0,
                  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_department_parent ON department(parent_id)")
            cur.execute(
                """
                INSERT INTO department(code, name_zh, name_en, parent_id, manager, description, sort_order)
                VALUES
                  ('cross_border', 'Cross-Border Data', 'Cross-Border', NULL, 'Mercy', 'Default cross-border commerce team', 10),
                  ('foreign_trade', 'Foreign Trade', 'Foreign Trade', NULL, NULL, 'Traditional foreign trade team', 20),
                  ('sourcing', 'Sourcing', 'Sourcing', NULL, NULL, 'Product research and sourcing team', 30),
                  ('operations', 'Operations', 'Operations', NULL, NULL, 'Operations and support team', 40)
                ON CONFLICT (code) DO NOTHING
                """
            )
            results.append(("department", "table/index/seeds ready"))

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS api_metric (
                  id BIGSERIAL PRIMARY KEY,
                  endpoint TEXT NOT NULL,
                  method TEXT NOT NULL DEFAULT 'GET',
                  day TEXT NOT NULL,
                  hour BIGINT NOT NULL DEFAULT 0,
                  call_count BIGINT NOT NULL DEFAULT 0,
                  error_count BIGINT NOT NULL DEFAULT 0,
                  total_ms BIGINT NOT NULL DEFAULT 0,
                  p99_ms BIGINT,
                  last_called_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(endpoint, method, day, hour)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_api_metric_day ON api_metric(day)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_api_metric_endpoint ON api_metric(endpoint)")
            results.append(("api_metric", "table/index ready"))

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_token_usage (
                  id BIGSERIAL PRIMARY KEY,
                  provider_code TEXT NOT NULL,
                  model TEXT,
                  feature TEXT,
                  day TEXT NOT NULL,
                  input_tokens BIGINT NOT NULL DEFAULT 0,
                  output_tokens BIGINT NOT NULL DEFAULT 0,
                  call_count BIGINT NOT NULL DEFAULT 0,
                  error_count BIGINT NOT NULL DEFAULT 0,
                  total_cost_usd DOUBLE PRECISION DEFAULT 0,
                  last_used_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(provider_code, model, feature, day)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_day ON llm_token_usage(day)")
            results.append(("llm_token_usage", "table/index ready"))

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS business_metric_daily (
                  id BIGSERIAL PRIMARY KEY,
                  day TEXT NOT NULL,
                  scope_kind TEXT NOT NULL,
                  scope_id TEXT,
                  creators_total BIGINT DEFAULT 0,
                  creators_new BIGINT DEFAULT 0,
                  creators_active BIGINT DEFAULT 0,
                  creators_prospect BIGINT DEFAULT 0,
                  outreach_total BIGINT DEFAULT 0,
                  outreach_new BIGINT DEFAULT 0,
                  contacted_count BIGINT DEFAULT 0,
                  confirmed_count BIGINT DEFAULT 0,
                  sample_shipped BIGINT DEFAULT 0,
                  video_published BIGINT DEFAULT 0,
                  ad_running BIGINT DEFAULT 0,
                  conversion_rate DOUBLE PRECISION DEFAULT 0,
                  avg_response_hours DOUBLE PRECISION,
                  gmv_30d_usd DOUBLE PRECISION DEFAULT 0,
                  computed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(day, scope_kind, scope_id)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_biz_metric_day ON business_metric_daily(day)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_biz_metric_scope ON business_metric_daily(scope_kind, scope_id)")
            results.append(("business_metric_daily", "table/index ready"))

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS notification (
                  id BIGSERIAL PRIMARY KEY,
                  recipient TEXT NOT NULL,
                  title TEXT NOT NULL,
                  body TEXT,
                  level TEXT NOT NULL DEFAULT 'info',
                  category TEXT,
                  link_url TEXT,
                  related_table TEXT,
                  related_id BIGINT,
                  read_at TIMESTAMPTZ,
                  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notification_recipient ON notification(recipient)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_notification_unread ON notification(recipient, read_at)")
            cur.execute("SELECT COUNT(*) FROM notification")
            if int(cur.fetchone()[0]) == 0:
                cur.execute(
                    """
                    INSERT INTO notification(recipient, title, body, level, category, link_url)
                    VALUES
                      ('*', 'API v1 is now backed by PostgreSQL', 'React admin data routes now read PostgreSQL resources.', 'info', 'system', '/a/api-stats'),
                      ('*', 'UI support tables are ready', 'Departments, notifications, API metrics, LLM usage, and business metrics are registered.', 'success', 'system', '/a/resources'),
                      ('Mercy', 'Today outreach queue is ready', 'Open the dashboard to review creators waiting for contact.', 'info', 'outreach', '/d/dashboard')
                    """
                )
                results.append(("notification", "seeded 3 rows"))
            results.append(("notification", "table/index ready"))

            for target in ("creator", "staff", "outreach"):
                add_department_id(cur, target, results)

            cur.execute("SELECT id FROM department WHERE code = 'cross_border'")
            default_department = cur.fetchone()
            if default_department:
                default_department_id = default_department[0]
                for target in ("creator", "staff", "outreach"):
                    if table_exists(cur, target) and column_exists(cur, target, "department_id"):
                        cur.execute(
                            sql.SQL("UPDATE {} SET department_id = %s WHERE department_id IS NULL").format(
                                sql.Identifier(target)
                            ),
                            (default_department_id,),
                        )
                        results.append((f"{target}.department_id", f"backfilled {cur.rowcount} rows"))

            register_resource(
                cur,
                name="departments",
                table_name="department",
                description="Organization departments for the admin UI.",
                writable=True,
            )
            register_resource(
                cur,
                name="api_metrics",
                table_name="api_metric",
                description="API call metrics for the admin UI.",
                writable=False,
            )
            register_resource(
                cur,
                name="llm_token_usages",
                table_name="llm_token_usage",
                description="LLM token usage by provider/model/feature/day.",
                writable=False,
            )
            register_resource(
                cur,
                name="business_metrics_daily",
                table_name="business_metric_daily",
                description="Daily business KPI snapshots.",
                writable=False,
            )
            register_resource(
                cur,
                name="notifications",
                table_name="notification",
                description="In-app notifications for the React admin UI.",
                writable=True,
            )
            results.append(("_meta_resource", "5 UI support resources registered"))

            upsert_pg_queries(cur)
            results.append(("_meta_query", f"{len(PG_QUERIES)} PostgreSQL queries upserted"))

        con.commit()
    return {"ok": True, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN, help="PostgreSQL DSN")
    args = parser.parse_args()
    summary = migrate(args.pg_dsn)
    print("[migrate_v20] complete")
    for key, value in summary["results"]:
        print(f"  {key:32s} {value}")


if __name__ == "__main__":
    main()
