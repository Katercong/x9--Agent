"""migrate_v12 — 撤销 v11 留下的 creators (lead 池) + creator_leads slug

背景：v3.8.1 决策 — 廖另建了 `tk_creators` 表（130 行）作为 lead 池，
v11 建的 `creators` 表 + `creator_leads` URL slug 闲置，前端已 repoint 到 tk_creators。

操作：
  1. 删 _meta_resource 里的 creator_leads 注册
  2. 仅当 `creators` 表为空时 drop（防止误删廖未来新数据）

幂等。再跑无副作用（已删的不会再删）。

注意 migrate_v11.py 已同步移除 creators / creator_leads 创建逻辑，
所以下次启动不会重建。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "database.db"


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        # 1. 移除 creator_leads slug 注册（如果还在）
        deleted_meta = con.execute(
            "DELETE FROM _meta_resource WHERE name='creator_leads'"
        ).rowcount
        if deleted_meta:
            print(f"[migrate_v12] removed creator_leads slug from _meta_resource ({deleted_meta} row)")
        else:
            print("[migrate_v12] creator_leads slug already gone")

        # 2. drop creators 表（仅当为空，避免误删廖将来真在用）
        existing = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='creators'"
        ).fetchone()
        if existing:
            n = con.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
            if n == 0:
                con.execute("DROP TABLE creators")
                print("[migrate_v12] dropped empty creators table (lead pool was unused; tk_creators is canonical)")
            else:
                print(f"[migrate_v12] creators table has {n} rows — refusing to drop. Manual review needed.")
        else:
            print("[migrate_v12] creators table already gone")

        con.commit()
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
