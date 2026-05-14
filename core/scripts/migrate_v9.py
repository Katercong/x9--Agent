"""Schema migration v9: TK 热搜关键词 + 标题优化器（任务 2.2.2）

新增：
- tk_hot_keyword 表：存储廖的爬虫产出的热搜关键词
- 注册为通用 CRUD resource (廖那边 POST /api/v1/data/tk_hot_keywords/bulk 即可)
- 在 llm_feature 加 title_optimizer 行（独立绑定模型）
- 种入 ~24 条 bootstrap 关键词（4 类目 × 6 个示意词），方便张在廖爬虫上线前先跑通；
  这些种子打 `notes='bootstrap_seed'`，廖的爬虫覆盖时根据 keyword+platform+region UPSERT 即可

Idempotent.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"


CREATE_KEYWORD = """
CREATE TABLE IF NOT EXISTS tk_hot_keyword (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT NOT NULL,
    source_platform TEXT NOT NULL DEFAULT 'tiktok',     -- tiktok / temu / ebay / amazon / google
    region          TEXT NOT NULL DEFAULT 'US',          -- US / UK / MX / SEA / ...
    category_hint   TEXT,                                -- female_care / pet / baby / adult_care / home_care / mask / null
    search_volume   INTEGER,                             -- 估计搜索量
    growth_rate     REAL,                                -- 周环比增长 (-1.0 ~ 10.0+)
    rank_position   INTEGER,                             -- 抓取时的榜单名次
    raw_metrics     TEXT,                                -- JSON 原始数据 (留给廖)
    sample_evidence TEXT,                                -- JSON: 相关 top 视频/listing
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_kw_platform_region ON tk_hot_keyword(source_platform, region)",
    "CREATE INDEX IF NOT EXISTS idx_kw_category ON tk_hot_keyword(category_hint, is_active)",
    "CREATE INDEX IF NOT EXISTS idx_kw_recent ON tk_hot_keyword(last_seen_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_kw_keyword_platform_region "
    "ON tk_hot_keyword(keyword, source_platform, region)",
]

RESOURCE_ROW = (
    "tk_hot_keywords", "tk_hot_keyword", "id",
    ["keyword", "source_platform", "region"],     # upsert keys
    ["raw_metrics", "sample_evidence"],            # json cols
    {},
    "TK 热搜关键词（廖爬虫产出，POST /api/v1/data/tk_hot_keywords/bulk 写入）"
)

# Bootstrap seeds — illustrative only. 廖's scraper will UPSERT real data over these.
NOW = datetime.utcnow().strftime("%Y-%m-%d")
SEEDS = [
    # female_care
    {"keyword": "period underwear", "category_hint": "female_care",
     "search_volume": 220000, "growth_rate": 0.18, "rank_position": 4},
    {"keyword": "organic cotton pads", "category_hint": "female_care",
     "search_volume": 95000, "growth_rate": 0.34, "rank_position": 12},
    {"keyword": "fragrance free pads", "category_hint": "female_care",
     "search_volume": 68000, "growth_rate": 0.21, "rank_position": 18},
    {"keyword": "overnight pads heavy flow", "category_hint": "female_care",
     "search_volume": 42000, "growth_rate": 0.45, "rank_position": 22},
    {"keyword": "panty liners daily", "category_hint": "female_care",
     "search_volume": 31000, "growth_rate": 0.08, "rank_position": 35},
    {"keyword": "sensitive skin pads", "category_hint": "female_care",
     "search_volume": 28000, "growth_rate": 0.27, "rank_position": 41},
    # pet
    {"keyword": "dog diapers male", "category_hint": "pet",
     "search_volume": 88000, "growth_rate": 0.42, "rank_position": 8},
    {"keyword": "female dog diapers", "category_hint": "pet",
     "search_volume": 72000, "growth_rate": 0.31, "rank_position": 11},
    {"keyword": "puppy pads xl", "category_hint": "pet",
     "search_volume": 56000, "growth_rate": 0.19, "rank_position": 19},
    {"keyword": "leak proof dog pad", "category_hint": "pet",
     "search_volume": 41000, "growth_rate": 0.28, "rank_position": 24},
    {"keyword": "training pads for dogs", "category_hint": "pet",
     "search_volume": 64000, "growth_rate": 0.13, "rank_position": 16},
    {"keyword": "dog diaper heat cycle", "category_hint": "pet",
     "search_volume": 33000, "growth_rate": 0.51, "rank_position": 28},
    # baby
    {"keyword": "ultra thin baby diapers", "category_hint": "baby",
     "search_volume": 47000, "growth_rate": 0.16, "rank_position": 23},
    {"keyword": "newborn diapers organic", "category_hint": "baby",
     "search_volume": 38000, "growth_rate": 0.22, "rank_position": 31},
    {"keyword": "training pants toddler", "category_hint": "baby",
     "search_volume": 51000, "growth_rate": 0.11, "rank_position": 20},
    {"keyword": "nursing pads disposable", "category_hint": "baby",
     "search_volume": 24000, "growth_rate": 0.19, "rank_position": 38},
    # adult_care
    {"keyword": "adult pull up underwear", "category_hint": "adult_care",
     "search_volume": 62000, "growth_rate": 0.14, "rank_position": 17},
    {"keyword": "incontinence pads men", "category_hint": "adult_care",
     "search_volume": 49000, "growth_rate": 0.23, "rank_position": 21},
    {"keyword": "postpartum pads maxi", "category_hint": "adult_care",
     "search_volume": 35000, "growth_rate": 0.36, "rank_position": 26},
    {"keyword": "bladder leak pads women", "category_hint": "adult_care",
     "search_volume": 41000, "growth_rate": 0.18, "rank_position": 25},
    # home_care
    {"keyword": "bed pads for incontinence", "category_hint": "home_care",
     "search_volume": 39000, "growth_rate": 0.22, "rank_position": 27},
    {"keyword": "underpads disposable", "category_hint": "home_care",
     "search_volume": 28000, "growth_rate": 0.16, "rank_position": 33},
    {"keyword": "charcoal pet pads", "category_hint": "home_care",
     "search_volume": 19000, "growth_rate": 0.41, "rank_position": 44},
    {"keyword": "lavender training pads", "category_hint": "home_care",
     "search_volume": 14000, "growth_rate": 0.29, "rank_position": 52},
]


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(CREATE_KEYWORD)
    for idx in CREATE_INDEXES:
        try:
            con.execute(idx)
        except sqlite3.OperationalError:
            pass

    # Register resource
    name, table, pk, upsert, json_cols, fk, desc = RESOURCE_ROW
    con.execute(
        "INSERT INTO _meta_resource(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
        "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
        "ON CONFLICT(name) DO UPDATE SET upsert_keys=excluded.upsert_keys, "
        "json_cols=excluded.json_cols, description=excluded.description",
        (name, table, pk, json.dumps(upsert), json.dumps(json_cols), json.dumps(fk), desc)
    )

    # Add llm_feature row
    con.execute(
        "INSERT INTO llm_feature(code, display_name, description, sort_order) "
        "VALUES('title_optimizer', 'TK 标题热搜关键词优化', "
        "'按 TK 热搜关键词 + 产品卖点生成多个标题候选（电商 SEO）', 3) "
        "ON CONFLICT(code) DO UPDATE SET display_name=excluded.display_name, "
        "description=excluded.description"
    )

    # Seed bootstrap keywords (idempotent by unique index keyword+platform+region)
    n_added = 0
    for s in SEEDS:
        cur = con.execute(
            "INSERT OR IGNORE INTO tk_hot_keyword"
            "(keyword, source_platform, region, category_hint, search_volume, "
            "growth_rate, rank_position, first_seen_at, last_seen_at, notes) "
            "VALUES(?, 'tiktok', 'US', ?, ?, ?, ?, ?, ?, 'bootstrap_seed - replace with scraper data')",
            (s["keyword"], s["category_hint"], s["search_volume"],
             s["growth_rate"], s["rank_position"], NOW, NOW)
        )
        n_added += cur.rowcount

    con.commit()

    n_total = con.execute("SELECT COUNT(*) FROM tk_hot_keyword").fetchone()[0]
    by_cat = con.execute(
        "SELECT category_hint, COUNT(*) FROM tk_hot_keyword "
        "WHERE is_active=1 GROUP BY category_hint ORDER BY 1"
    ).fetchall()
    print(f"[migrate_v9] tk_hot_keyword table ready, +{n_added} bootstrap seeds")
    print(f"[migrate_v9] total: {n_total} keywords")
    for cat, cnt in by_cat:
        print(f"   {cat or '(no category)':16s} {cnt}")
    print(f"[migrate_v9] llm_feature 'title_optimizer' registered")
    con.close()


if __name__ == "__main__":
    main()
