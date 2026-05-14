"""migrate_v15: webhook_subscriber 表 (钉钉 / 通用 HTTP webhook)

订阅者表，用于 schema 变更时推送通知。每条订阅者：
  - kind = 'dingtalk' | 'http'
  - url  = webhook 地址
  - secret = 钉钉加签密钥（可选; 不填则需要在群机器人配置里加关键词）
  - keyword = 关键词模式必备（钉钉群机器人安全设置: 关键词）
  - events = JSON array, null=所有事件
  - active = 1 默认开

幂等。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "database.db"


def main() -> None:
    con = sqlite3.connect(DB)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS webhook_subscriber(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'dingtalk',
                url TEXT NOT NULL,
                secret TEXT,
                keyword TEXT,
                events TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                last_fired_at TEXT,
                last_status TEXT,
                last_error TEXT,
                UNIQUE(name)
            )
        """)
        # 注册成 generic CRUD resource (admin 可以从前台管理)
        con.execute("""
            INSERT OR IGNORE INTO _meta_resource(name, table_name, pk, upsert_keys, json_cols, fk_lookup, writable, is_dynamic, description)
            VALUES('webhooks', 'webhook_subscriber', 'id', '["name"]', '["events"]', '{}', 'schema 变更/重要事件 webhook 订阅者（钉钉机器人 URL）', 0, 1)
        """)
        con.commit()
        print("[migrate_v15] webhook_subscriber table ready")
    finally:
        con.close()


if __name__ == "__main__":
    main()
