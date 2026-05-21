"""Import one normalized creator shop page JSON into v19 tables.

The expected JSON shape matches the page extraction summary:
  creator_profile, promotion_performance_score, sample_score,
  sales_performance, collaboration_metrics, video_performance,
  live_performance, audience_profile, trend_metrics_available,
  example_videos, similar_creators, business_analysis.

Usage:
  py core/scripts/import_creator_shop_snapshot.py holaimshirley.json
  type holaimshirley.json | py core/scripts/import_creator_shop_snapshot.py -
  py core/scripts/import_creator_shop_snapshot.py holaimshirley.json --postgres
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from migrate_v19_creator_shop_profile import DEFAULT_PG_DSN, DEFAULT_SQLITE, migrate_postgres, migrate_sqlite


COMPACT_NUMBER_RE = re.compile(r"^\s*\$?\s*([0-9]+(?:\.[0-9]+)?)\s*([KMBkmb]?)\s*$")


def parse_compact_number(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or "-" in text:
        return None
    match = COMPACT_NUMBER_RE.match(text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2).lower()
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
    return int(round(number * multiplier))


def parse_date_range(value: Any) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = [part.strip() for part in str(value).split(" - ", 1)]
    if len(parts) != 2:
        return None, None
    return parse_page_date(parts[0]), parse_page_date(parts[1])


def parse_page_date(value: str) -> str | None:
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return value.strip() or None


def dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def clean_handle(value: Any) -> str:
    return str(value or "").strip().lstrip("@")


def first_metric_range(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    for key in ("sample_score", "sales_performance", "video_performance", "live_performance"):
        block = payload.get(key) or {}
        start, end = parse_date_range(block.get("date_range"))
        if start or end:
            return start, end, block.get("timezone")
    return None, None, None


def sub_score(block: dict[str, Any], key: str, field: str) -> Any:
    return ((block.get("sub_scores") or {}).get(key) or {}).get(field)


def build_snapshot_row(payload: dict[str, Any], creator_ref: dict[str, Any]) -> dict[str, Any]:
    profile = payload.get("creator_profile") or {}
    pps = payload.get("promotion_performance_score") or {}
    sample = payload.get("sample_score") or {}
    sales = payload.get("sales_performance") or {}
    collab = payload.get("collaboration_metrics") or {}
    video = payload.get("video_performance") or {}
    live = payload.get("live_performance") or {}
    analysis = payload.get("business_analysis") or {}
    start, end, timezone = first_metric_range(payload)
    handle = clean_handle(profile.get("account_handle") or creator_ref.get("handle"))

    return {
        "creator_source_table": creator_ref.get("table"),
        "creator_id": str(creator_ref.get("id")) if creator_ref.get("id") is not None else None,
        "platform": creator_ref.get("platform") or "tiktok",
        "handle": handle,
        "account_handle": handle,
        "display_name": profile.get("display_name"),
        "rating": profile.get("rating"),
        "main_category": profile.get("main_category"),
        "additional_categories_count": profile.get("additional_categories_count"),
        "followers_raw": profile.get("followers"),
        "bio": profile.get("bio"),
        "location_or_identity_text": profile.get("location_or_identity_text"),
        "email": profile.get("email"),
        "instagram_handle": profile.get("instagram"),
        "external_link": profile.get("external_link"),
        "flat_fee_eligibility": profile.get("flat_fee_eligibility"),
        "invite_status": profile.get("invite_status"),
        "pps_score": pps.get("pps_score"),
        "pps_max_score": pps.get("pps_max_score"),
        "pps_level": pps.get("pps_level"),
        "pps_description": pps.get("description"),
        "metric_start_date": start,
        "metric_end_date": end,
        "metric_timezone": timezone,
        "sample_score_total": sample.get("total_score"),
        "sample_score_max": sample.get("max_score"),
        "sample_score_level": sample.get("level"),
        "posts_with_samples_score": sub_score(sample, "posts_with_samples", "score"),
        "posts_with_samples_level": sub_score(sample, "posts_with_samples", "level"),
        "posts_with_samples_comparison": sub_score(sample, "posts_with_samples", "comparison"),
        "post_frequency_score": sub_score(sample, "post_frequency", "score"),
        "post_frequency_level": sub_score(sample, "post_frequency", "level"),
        "post_frequency_comparison": sub_score(sample, "post_frequency", "comparison"),
        "sales_generation_score": sub_score(sample, "sales_generation", "score"),
        "sales_generation_level": sub_score(sample, "sales_generation", "level"),
        "sales_generation_comparison": sub_score(sample, "sales_generation", "comparison"),
        "content_quality_score": sub_score(sample, "content_quality", "score"),
        "content_quality_level": sub_score(sample, "content_quality", "level"),
        "content_quality_comparison": sub_score(sample, "content_quality", "comparison"),
        "gmv_range": sales.get("gmv"),
        "items_sold_range": sales.get("items_sold"),
        "gpm_range": sales.get("gpm"),
        "gmv_per_customer_range": sales.get("gmv_per_customer"),
        "gmv_per_sales_channel_json": dumps(sales.get("gmv_per_sales_channel")),
        "estimated_post_rate": collab.get("estimated_post_rate"),
        "average_commission_rate": collab.get("average_commission_rate"),
        "products_json": dumps(collab.get("products")),
        "brand_collaborations_json": dumps(collab.get("brand_collaborations")),
        "video_gpm_range": video.get("video_gpm"),
        "videos_count": video.get("videos_count"),
        "average_video_views": video.get("average_video_views"),
        "average_video_engagement_rate": video.get("average_video_engagement_rate"),
        "live_gpm_range": live.get("live_gpm"),
        "live_streams_count": live.get("live_streams_count"),
        "average_live_views": live.get("average_live_views"),
        "average_live_engagement_rate": live.get("average_live_engagement_rate"),
        "audience_profile_json": dumps(payload.get("audience_profile")),
        "trend_metrics_json": dumps(payload.get("trend_metrics_available")),
        "creator_type": analysis.get("creator_type"),
        "main_strengths_json": dumps(analysis.get("main_strengths")),
        "main_weaknesses_json": dumps(analysis.get("main_weaknesses")),
        "recommended_cooperation_type_json": dumps(analysis.get("recommended_cooperation_type")),
        "risk_level": analysis.get("risk_level"),
        "priority_level": analysis.get("priority_level"),
        "raw_json": dumps(payload),
    }


def snapshot_latest_fields(row: dict[str, Any], snapshot_id: int) -> dict[str, Any]:
    return {
        "shop_account_handle": row.get("account_handle"),
        "shop_rating": row.get("rating"),
        "shop_main_category": row.get("main_category"),
        "shop_additional_categories_count": row.get("additional_categories_count"),
        "shop_location_or_identity_text": row.get("location_or_identity_text"),
        "shop_instagram_handle": row.get("instagram_handle"),
        "shop_external_link": row.get("external_link"),
        "shop_flat_fee_eligibility": row.get("flat_fee_eligibility"),
        "shop_invite_status": row.get("invite_status"),
        "shop_pps_score": row.get("pps_score"),
        "shop_pps_level": row.get("pps_level"),
        "shop_sample_score": row.get("sample_score_total"),
        "shop_sample_level": row.get("sample_score_level"),
        "shop_gmv_range": row.get("gmv_range"),
        "shop_items_sold_range": row.get("items_sold_range"),
        "shop_gpm_range": row.get("gpm_range"),
        "shop_gmv_per_customer_range": row.get("gmv_per_customer_range"),
        "shop_estimated_post_rate": row.get("estimated_post_rate"),
        "shop_average_commission_rate": row.get("average_commission_rate"),
        "shop_videos_count": row.get("videos_count"),
        "shop_average_video_views": row.get("average_video_views"),
        "shop_average_video_engagement_rate": row.get("average_video_engagement_rate"),
        "shop_live_streams_count": row.get("live_streams_count"),
        "shop_average_live_views": row.get("average_live_views"),
        "shop_average_live_engagement_rate": row.get("average_live_engagement_rate"),
        "shop_latest_snapshot_id": str(snapshot_id),
        "shop_latest_snapshot_at": datetime.now().isoformat(timespec="seconds"),
    }


def read_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    return payload


def sqlite_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}


def sqlite_table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def sqlite_lookup_creator(con: sqlite3.Connection, platform: str, handle: str) -> dict[str, Any]:
    for table in ("tk_creators", "creators", "creator"):
        if not sqlite_table_exists(con, table):
            continue
        row = con.execute(
            f'SELECT id, platform, handle FROM "{table}" WHERE platform=? AND lower(handle)=lower(?) LIMIT 1',
            (platform, handle),
        ).fetchone()
        if row:
            return {"table": table, "id": row[0], "platform": row[1], "handle": row[2]}
    return {"table": "tk_creators", "id": None, "platform": platform, "handle": handle}


def sqlite_insert(con: sqlite3.Connection, table: str, fields: dict[str, Any]) -> int:
    cols = list(fields)
    placeholders = ",".join(["?"] * len(cols))
    cur = con.execute(
        f'INSERT INTO "{table}" ({",".join(cols)}) VALUES ({placeholders})',
        [fields[col] for col in cols],
    )
    return int(cur.lastrowid)


def sqlite_insert_or_ignore(con: sqlite3.Connection, table: str, fields: dict[str, Any]) -> None:
    cols = list(fields)
    placeholders = ",".join(["?"] * len(cols))
    con.execute(
        f'INSERT OR IGNORE INTO "{table}" ({",".join(cols)}) VALUES ({placeholders})',
        [fields[col] for col in cols],
    )


def sqlite_update_latest(con: sqlite3.Connection, platform: str, handle: str, fields: dict[str, Any]) -> list[str]:
    updated: list[str] = []
    for table in ("tk_creators", "creators", "creator"):
        if not sqlite_table_exists(con, table):
            continue
        cols = sqlite_columns(con, table)
        clean = {k: v for k, v in fields.items() if k in cols}
        if not clean:
            continue
        sets = ", ".join([f'"{k}"=?' for k in clean])
        cur = con.execute(
            f'UPDATE "{table}" SET {sets} WHERE platform=? AND lower(handle)=lower(?)',
            list(clean.values()) + [platform, handle],
        )
        if cur.rowcount:
            updated.append(table)
    return updated


def import_sqlite(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    migrate_sqlite(db_path)
    con = sqlite3.connect(db_path)
    try:
        profile = payload.get("creator_profile") or {}
        platform = "tiktok"
        handle = clean_handle(profile.get("account_handle"))
        if not handle:
            raise ValueError("creator_profile.account_handle is required")
        creator_ref = sqlite_lookup_creator(con, platform, handle)
        snapshot = build_snapshot_row(payload, creator_ref)
        snapshot_id = sqlite_insert(con, "creator_shop_snapshots", snapshot)

        for item in payload.get("sales_performance", {}).get("gmv_category_distribution") or []:
            sqlite_insert_or_ignore(con, "creator_shop_category_distribution", {
                "snapshot_id": snapshot_id,
                "category": item.get("category"),
                "percentage": item.get("percentage"),
            })
        for item in payload.get("example_videos") or []:
            sqlite_insert_or_ignore(con, "creator_shop_example_videos", {
                "snapshot_id": snapshot_id,
                "creator_id": snapshot.get("creator_id"),
                "platform": platform,
                "handle": handle,
                "caption_or_title": item.get("caption_or_title"),
                "publish_date": item.get("publish_date"),
                "views_raw": item.get("views"),
                "views_count": parse_compact_number(item.get("views")),
                "engagement_or_likes_raw": item.get("engagement_or_likes"),
                "engagement_or_likes_count": parse_compact_number(item.get("engagement_or_likes")),
                "has_product_link": 1 if item.get("has_product_link") else 0,
                "action_available": item.get("action_available"),
            })
        for item in payload.get("similar_creators") or []:
            sqlite_insert_or_ignore(con, "creator_shop_similar_creators", {
                "snapshot_id": snapshot_id,
                "account_handle": clean_handle(item.get("account_handle")),
                "tag": item.get("tag"),
                "pps_score": item.get("pps_score"),
                "pps_max_score": item.get("pps_max_score"),
                "category": item.get("category"),
                "followers_raw": item.get("followers"),
                "followers_count": parse_compact_number(item.get("followers")),
                "gmv_raw": item.get("gmv"),
                "items_sold_raw": item.get("items_sold"),
                "items_sold_count": parse_compact_number(item.get("items_sold")),
                "average_views_raw": item.get("average_views"),
                "average_views_count": parse_compact_number(item.get("average_views")),
            })

        updated_tables = sqlite_update_latest(con, platform, handle, snapshot_latest_fields(snapshot, snapshot_id))
        con.commit()
        return {"snapshot_id": snapshot_id, "handle": handle, "updated_main_tables": updated_tables}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def pg_columns(cur: psycopg.Cursor, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


def pg_table_exists(cur: psycopg.Cursor, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return cur.fetchone() is not None


def pg_lookup_creator(cur: psycopg.Cursor, platform: str, handle: str) -> dict[str, Any]:
    for table in ("tk_creators", "creators", "creator"):
        if not pg_table_exists(cur, table):
            continue
        cur.execute(
            sql.SQL("SELECT id, platform, handle FROM {} WHERE platform=%s AND lower(handle)=lower(%s) LIMIT 1")
            .format(sql.Identifier(table)),
            (platform, handle),
        )
        row = cur.fetchone()
        if row:
            return {"table": table, "id": row[0], "platform": row[1], "handle": row[2]}
    return {"table": "tk_creators", "id": None, "platform": platform, "handle": handle}


def pg_insert(cur: psycopg.Cursor, table: str, fields: dict[str, Any]) -> int:
    cols = list(fields)
    cur.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING id").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(col) for col in cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in cols),
        ),
        [fields[col] for col in cols],
    )
    return int(cur.fetchone()[0])


def pg_insert_do_nothing(cur: psycopg.Cursor, table: str, fields: dict[str, Any], conflict_cols: list[str]) -> None:
    cols = list(fields)
    cur.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO NOTHING").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(col) for col in cols),
            sql.SQL(", ").join(sql.Placeholder() for _ in cols),
            sql.SQL(", ").join(sql.Identifier(col) for col in conflict_cols),
        ),
        [fields[col] for col in cols],
    )


def pg_update_latest(cur: psycopg.Cursor, platform: str, handle: str, fields: dict[str, Any]) -> list[str]:
    updated: list[str] = []
    for table in ("tk_creators", "creators", "creator"):
        if not pg_table_exists(cur, table):
            continue
        cols = pg_columns(cur, table)
        clean = {k: v for k, v in fields.items() if k in cols}
        if not clean:
            continue
        cur.execute(
            sql.SQL("UPDATE {} SET {} WHERE platform=%s AND lower(handle)=lower(%s)").format(
                sql.Identifier(table),
                sql.SQL(", ").join(
                    sql.SQL("{} = {}").format(sql.Identifier(col), sql.Placeholder())
                    for col in clean
                ),
            ),
            list(clean.values()) + [platform, handle],
        )
        if cur.rowcount:
            updated.append(table)
    return updated


def import_postgres(dsn: str, payload: dict[str, Any]) -> dict[str, Any]:
    migrate_postgres(dsn)
    with psycopg.connect(dsn) as con:
        try:
            with con.cursor() as cur:
                profile = payload.get("creator_profile") or {}
                platform = "tiktok"
                handle = clean_handle(profile.get("account_handle"))
                if not handle:
                    raise ValueError("creator_profile.account_handle is required")
                creator_ref = pg_lookup_creator(cur, platform, handle)
                snapshot = build_snapshot_row(payload, creator_ref)
                snapshot_id = pg_insert(cur, "creator_shop_snapshots", snapshot)

                for item in payload.get("sales_performance", {}).get("gmv_category_distribution") or []:
                    pg_insert_do_nothing(cur, "creator_shop_category_distribution", {
                        "snapshot_id": snapshot_id,
                        "category": item.get("category"),
                        "percentage": item.get("percentage"),
                    }, ["snapshot_id", "category"])
                for item in payload.get("example_videos") or []:
                    pg_insert_do_nothing(cur, "creator_shop_example_videos", {
                        "snapshot_id": snapshot_id,
                        "creator_id": snapshot.get("creator_id"),
                        "platform": platform,
                        "handle": handle,
                        "caption_or_title": item.get("caption_or_title"),
                        "publish_date": item.get("publish_date"),
                        "views_raw": item.get("views"),
                        "views_count": parse_compact_number(item.get("views")),
                        "engagement_or_likes_raw": item.get("engagement_or_likes"),
                        "engagement_or_likes_count": parse_compact_number(item.get("engagement_or_likes")),
                        "has_product_link": 1 if item.get("has_product_link") else 0,
                        "action_available": item.get("action_available"),
                    }, ["snapshot_id", "caption_or_title", "publish_date"])
                for item in payload.get("similar_creators") or []:
                    pg_insert_do_nothing(cur, "creator_shop_similar_creators", {
                        "snapshot_id": snapshot_id,
                        "account_handle": clean_handle(item.get("account_handle")),
                        "tag": item.get("tag"),
                        "pps_score": item.get("pps_score"),
                        "pps_max_score": item.get("pps_max_score"),
                        "category": item.get("category"),
                        "followers_raw": item.get("followers"),
                        "followers_count": parse_compact_number(item.get("followers")),
                        "gmv_raw": item.get("gmv"),
                        "items_sold_raw": item.get("items_sold"),
                        "items_sold_count": parse_compact_number(item.get("items_sold")),
                        "average_views_raw": item.get("average_views"),
                        "average_views_count": parse_compact_number(item.get("average_views")),
                    }, ["snapshot_id", "account_handle"])

                updated_tables = pg_update_latest(cur, platform, handle, snapshot_latest_fields(snapshot, snapshot_id))
            con.commit()
            return {"snapshot_id": snapshot_id, "handle": handle, "updated_main_tables": updated_tables}
        except Exception:
            con.rollback()
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_file", help="JSON file path, or '-' for stdin.")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="SQLite database path.")
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN, help="PostgreSQL DSN.")
    parser.add_argument("--postgres", action="store_true", help="Import into PostgreSQL instead of SQLite.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = read_payload(args.json_file)
    if args.postgres:
        result = import_postgres(args.pg_dsn, payload)
    else:
        result = import_sqlite(Path(args.sqlite), payload)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
