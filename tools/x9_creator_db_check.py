"""x9_creator_db_check — 统一后 creators 表的健康检查。

跑这个工具可以看到:
  - `creators` 总行数、有 legacy_int_id 的行数(从 A 迁来的)、纯 B 来源
  - `creator` 旧表的总行数(应该等于 creators_with_legacy_int_id)
  - `creators.followers_count` 为 NULL 的行数
  - `tk_creators`(廖的 lead pool 镜像表)行数
  - `raw_observations`(扩展观察记录)总行数 + 最近一天的增量
  - 各种关键索引是否在

可以在 migrate_v16 之后跑、在每次端到端验证之前跑。
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg
from psycopg.rows import dict_row


DEFAULT_PG_DSN = os.environ.get(
    "X9_PG_DSN",
    "postgresql://x9:x9_local_dev_2026@localhost:15432/x9db?connect_timeout=5",
)


def fetch_one(cur: psycopg.Cursor, sql: str, args: tuple = ()) -> dict | None:
    cur.execute(sql, args)
    return cur.fetchone()


def report(cur: psycopg.Cursor) -> None:
    sections: list[tuple[str, str]] = []

    # creators 表
    sections.append(("creators total", "SELECT COUNT(*) AS n FROM creators"))
    sections.append((
        "creators with legacy_int_id (= A merged into B)",
        "SELECT COUNT(*) AS n FROM creators WHERE legacy_int_id IS NOT NULL",
    ))
    sections.append((
        "creators pure-B (no legacy_int_id)",
        "SELECT COUNT(*) AS n FROM creators WHERE legacy_int_id IS NULL",
    ))
    sections.append((
        "creators followers_count NULL",
        "SELECT COUNT(*) AS n FROM creators WHERE followers_count IS NULL",
    ))
    sections.append((
        "creators with email",
        "SELECT COUNT(*) AS n FROM creators WHERE COALESCE(email,'') <> ''",
    ))

    # 旧 creator 表
    sections.append(("creator (legacy) total", "SELECT COUNT(*) AS n FROM creator"))

    # tk_creators(廖的 lead pool 镜像)
    sections.append(("tk_creators total", "SELECT COUNT(*) AS n FROM tk_creators"))

    # raw_observations(扩展接入)
    sections.append((
        "raw_observations total",
        "SELECT COUNT(*) AS n FROM raw_observations",
    ))
    sections.append((
        "raw_observations last 24h",
        # created_at 在 raw_observations 里是 TEXT 类型,所以要 CAST
        "SELECT COUNT(*) AS n FROM raw_observations WHERE created_at::timestamp > NOW() - INTERVAL '24 hours'",
    ))

    # 产品/建联
    sections.append(("product total", "SELECT COUNT(*) AS n FROM product"))
    sections.append(("outreach total", "SELECT COUNT(*) AS n FROM outreach"))
    sections.append(("product_image total", "SELECT COUNT(*) AS n FROM product_image"))

    print("=" * 60)
    print("X9 数据库健康检查 (PostgreSQL x9db)")
    print("=" * 60)
    for label, sql in sections:
        try:
            row = fetch_one(cur, sql)
            n = row["n"] if row else "(no result)"
            print(f"  {label:<55} {n}")
        except psycopg.Error as exc:
            print(f"  {label:<55} ERROR: {exc}")

    # 关键索引
    print("\n关键索引:")
    cur.execute(
        """
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname IN (
            'idx_creators_legacy_int_id',
            'uq_creators_platform_handle',
            'uq_tk_creators_platform_handle_pg',
            'idx_creators_handle_pg',
            'idx_raw_observations_hash_pg'
          )
        ORDER BY indexname
        """
    )
    rows = cur.fetchall()
    for r in rows:
        print(f"  ✓ {r['indexname']}")
    expected = {
        "idx_creators_legacy_int_id",
        "uq_creators_platform_handle",
        "idx_creators_handle_pg",
        "idx_raw_observations_hash_pg",
    }
    found = {r["indexname"] for r in rows}
    missing = expected - found
    if missing:
        print(f"  ! missing: {', '.join(sorted(missing))}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()

    # autocommit:每个查询独立事务,某一条出错不会卡死后面的
    with psycopg.connect(args.dsn, row_factory=dict_row, autocommit=True) as con:
        with con.cursor() as cur:
            report(cur)
    return 0


if __name__ == "__main__":
    sys.exit(main())
