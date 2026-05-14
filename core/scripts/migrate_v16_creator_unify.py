"""migrate_v16: creator 表统一(PostgreSQL only)

把 A 的 `creator` 表的数据合并进 B 的 `creators` 表,作为 X9 系统的统一达人主表。

执行内容
--------
1. 给 `creators` 表加 A 独有的列(country / language / category_tags / avg_views /
   gmv_30d_usd / pps / sample_score / post_rate_est / whatsapp / instagram_handle /
   youtube_handle / source / quality_score / first_contact_date / last_contact_date /
   legacy_int_id)。所有 ADD COLUMN IF NOT EXISTS,幂等。

2. 把 `creator` 的每一行按 (platform, handle) 合并到 `creators`:
   - 已存在:UPDATE 把 A 的字段补到 B 的空白处(B 已有值不覆盖,通过 COALESCE 实现)
   - 不存在:INSERT 一条新记录,生成 UUID,`followers` -> `followers_count`,
     `id` 存到 `legacy_int_id`
   写一份合并报告到 stdout(insert / update 计数)。

3. 不 rename `creator` 表,不动 FK 关系。`creators` 成为新写入入口,
   `creator` 保留为只读历史(旧代码仍可查)。完整移植到 `creators` 是后续任务。

幂等。可重复运行,不会重复插入,不会覆盖 B 中已有的非空字段。

调用
----
  py core/scripts/migrate_v16_creator_unify.py
  py core/scripts/migrate_v16_creator_unify.py --dsn postgresql://...
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


DEFAULT_PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)


# A 独有的列(来自 F:\Database 原 schema)。
# 部分列在 B 的 creators 表里已经存在(current_status / store_assigned / owner_bd / notes / email),
# 这里只列 B 缺的。
A_ONLY_COLUMNS: list[tuple[str, str]] = [
    ("country", "TEXT"),
    ("language", "TEXT"),
    ("category_tags", "JSONB"),
    ("avg_views", "BIGINT"),
    ("gmv_30d_usd", "NUMERIC"),
    ("pps", "NUMERIC"),
    ("sample_score", "NUMERIC"),
    ("post_rate_est", "NUMERIC"),
    ("whatsapp", "TEXT"),
    ("instagram_handle", "TEXT"),
    ("youtube_handle", "TEXT"),
    ("source", "TEXT"),
    ("quality_score", "NUMERIC"),
    ("first_contact_date", "TIMESTAMP"),
    ("last_contact_date", "TIMESTAMP"),
    ("legacy_int_id", "INTEGER"),
]


def add_a_only_columns(cur: psycopg.Cursor) -> int:
    added = 0
    for col, col_type in A_ONLY_COLUMNS:
        cur.execute(
            sql.SQL("ALTER TABLE creators ADD COLUMN IF NOT EXISTS {} ").format(
                sql.Identifier(col)
            ) + sql.SQL(col_type)
        )
        added += 1
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_creators_legacy_int_id ON creators(legacy_int_id)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_creators_platform_handle ON creators(platform, handle)"
    )
    return added


# 列映射:`creator` 表列名 -> `creators` 表列名(差异部分)
# 其余同名直接搬。
COLUMN_RENAMES = {
    "followers": "followers_count",
    "id": "legacy_int_id",
}

# `creators` 表里 B 已经定义但 A 也有的字段(同名):这些字段会被合并(B 优先)。
# 不在这里列举,直接靠 SELECT * + 重命名即可。


def get_creator_columns(cur: psycopg.Cursor, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row["column_name"] for row in cur.fetchall()]


def merge_creator_to_creators(cur: psycopg.Cursor) -> dict[str, int]:
    """把 creator 表的每行合并进 creators。返回 {inserted, updated, total}。"""

    # 读取 creator 表所有列
    creator_cols = get_creator_columns(cur, "creator")
    creators_cols = set(get_creator_columns(cur, "creators"))

    # 构建 SELECT 列表 + 重命名:把 creator 的列重命名到 creators 对应的列
    select_pairs: list[tuple[str, str]] = []  # (src_col_in_creator, dst_col_in_creators)
    for src_col in creator_cols:
        dst_col = COLUMN_RENAMES.get(src_col, src_col)
        if dst_col in creators_cols:
            select_pairs.append((src_col, dst_col))

    # 拉数据(SELECT src AS dst,后续 row[dst] 直接取)
    select_sql = sql.SQL("SELECT {} FROM creator").format(
        sql.SQL(", ").join(
            sql.SQL("{} AS {}").format(sql.Identifier(s), sql.Identifier(d))
            for s, d in select_pairs
        )
    )
    cur.execute(select_sql)
    rows = cur.fetchall()
    total = len(rows)

    if total == 0:
        return {"inserted": 0, "updated": 0, "total": 0}

    inserted = 0
    updated = 0

    dst_cols = [d for _, d in select_pairs]
    needs_uuid_id = "id" in creators_cols and "id" not in dst_cols  # id 由 creators 主键提供

    for row in rows:
        platform = row.get("platform")
        handle = row.get("handle")
        if not platform or not handle:
            continue

        # 检查是否已存在
        cur.execute(
            "SELECT id FROM creators WHERE platform = %s AND handle = %s",
            (platform, handle),
        )
        existing = cur.fetchone()

        if existing:
            # UPDATE — 只填 B 表为 NULL 的字段(COALESCE 行为),不覆盖已有值
            update_pairs = []
            update_vals: list[Any] = []
            for dst_col in dst_cols:
                if dst_col == "id":
                    continue
                if dst_col in {"platform", "handle"}:
                    continue
                update_pairs.append(
                    sql.SQL("{c} = COALESCE({c}, %s)").format(c=sql.Identifier(dst_col))
                )
                update_vals.append(row[dst_col])
            if update_pairs:
                stmt = sql.SQL("UPDATE creators SET {} WHERE platform = %s AND handle = %s").format(
                    sql.SQL(", ").join(update_pairs)
                )
                cur.execute(stmt, update_vals + [platform, handle])
                updated += 1
        else:
            # INSERT — 新行,id 用 UUID(gen_random_uuid)
            cols_to_insert = [c for c in dst_cols if c != "id"]
            placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in cols_to_insert)
            vals = [row[c] for c in cols_to_insert]
            if needs_uuid_id:
                cols_to_insert = ["id"] + cols_to_insert
                placeholders = sql.SQL(", ").join(
                    [sql.SQL("gen_random_uuid()::text")]
                    + [sql.Placeholder() for _ in vals]
                )
            stmt = sql.SQL("INSERT INTO creators ({}) VALUES ({})").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in cols_to_insert),
                placeholders,
            )
            cur.execute(stmt, vals)
            inserted += 1

    return {"inserted": inserted, "updated": updated, "total": total}


def health_check(cur: psycopg.Cursor) -> dict[str, int | None]:
    cur.execute("SELECT COUNT(*) AS n FROM creators")
    total_creators = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM creators WHERE legacy_int_id IS NOT NULL")
    with_legacy = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM creators WHERE followers_count IS NULL")
    null_followers = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM creator")
    total_legacy = cur.fetchone()["n"]
    return {
        "creators_total": total_creators,
        "creators_with_legacy_int_id": with_legacy,
        "creators_null_followers_count": null_followers,
        "creator_legacy_total": total_legacy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_PG_DSN, help="PostgreSQL DSN")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would happen without committing"
    )
    args = parser.parse_args()

    print(f"[migrate_v16] connecting to {args.dsn.split('@')[-1]}")
    with psycopg.connect(args.dsn, row_factory=dict_row) as con:
        with con.cursor() as cur:
            print(f"[migrate_v16] step 1: adding A-only columns to creators")
            added = add_a_only_columns(cur)
            print(f"[migrate_v16]   {added} ADD COLUMN IF NOT EXISTS statements executed")

            print(f"[migrate_v16] step 2: merging creator -> creators (upsert by platform+handle)")
            counts = merge_creator_to_creators(cur)
            print(f"[migrate_v16]   {counts}")

            print(f"[migrate_v16] step 3: health check")
            h = health_check(cur)
            for k, v in h.items():
                print(f"[migrate_v16]   {k}: {v}")

            if args.dry_run:
                con.rollback()
                print("[migrate_v16] DRY RUN — rolled back")
                return 0

            con.commit()
            print("[migrate_v16] committed")
            return 0


if __name__ == "__main__":
    sys.exit(main())
