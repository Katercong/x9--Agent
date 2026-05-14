"""migrate_v18: 注册 product_clone LLM feature

在 llm_feature 表里插入 product_clone 功能条目。
管理员可在前台 Settings → LLM Features 里将它绑定到任意已配置的 Provider，
并覆盖 model / temperature / max_tokens。

幂等: INSERT OR IGNORE，重复运行安全。
"""
from __future__ import annotations
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "database.db"


def main() -> None:
    con = sqlite3.connect(DB)
    try:
        # 1. 注册 LLM feature
        con.execute("""
            INSERT OR IGNORE INTO llm_feature
                (code, display_name, description, enabled, model, temperature, max_tokens)
            VALUES (
                'product_clone',
                '商品裂变文案',
                '为同一产品生成多角度标题/描述/卖点变体，用于多链接铺货。绑定 OpenAI 或兼容接口，推荐 gpt-4o-mini。',
                1,
                'gpt-4o-mini',
                0.85,
                700
            )
        """)

        # 2. 运营风格预设表（幂等）
        con.execute("""
            CREATE TABLE IF NOT EXISTS product_clone_preset (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                store_code  TEXT,
                global_style TEXT,
                variants    TEXT NOT NULL DEFAULT '[]',
                created_by  TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(name)
            )
        """)

        con.commit()
        row = con.execute(
            "SELECT code, display_name, enabled, model FROM llm_feature WHERE code='product_clone'"
        ).fetchone()
        n_presets = con.execute("SELECT COUNT(*) FROM product_clone_preset").fetchone()[0]
        print(f"[migrate_v18] llm_feature: code={row[0]}, display_name={row[1]}, enabled={row[2]}, model={row[3]}")
        print(f"[migrate_v18] product_clone_preset table ready, rows: {n_presets}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
