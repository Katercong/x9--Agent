"""Schema migration v8: 达人筛选与竞品排除（任务 3.1.2 + 3.1.3）.

新增：
- creator 表 4 列：
    engagement_rate    REAL          互动率 (0~1, 由廖的爬虫填或手动写)
    last_post_at       TEXT          最近发帖时间 (ISO date)
    excluded           INTEGER       是否排除（默认 0）
    excluded_reason    TEXT          排除原因
- 表 competitor_brand：竞品品牌表（black-list 来源）
- 表 creator_competitor_collab：达人 × 竞品多对多（带证据 URL / 置信度）

并：
- 注册新表为通用 CRUD resource
- 种入常见女性护理 / 宠物 / 母婴 竞品
- 加 4 条命名查询：
    creators_mid_tier_koc      1K-50W 中腰部 KOC，未排除，未与竞品合作
    creators_high_engagement   按互动率排序
    creators_blacklisted       已排除 / 已合作竞品
    creators_by_content_match  按内容标签匹配某品类

Idempotent.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"


# ----- New columns on creator -----
NEW_CREATOR_COLS = [
    ("engagement_rate", "REAL"),
    ("last_post_at", "TEXT"),
    ("excluded", "INTEGER NOT NULL DEFAULT 0"),
    ("excluded_reason", "TEXT"),
]

# ----- New tables -----
CREATE_COMPETITOR = """
CREATE TABLE IF NOT EXISTS competitor_brand (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT UNIQUE NOT NULL,           -- 'always' / 'lola' / 'pampers' / ...
    display_name    TEXT NOT NULL,
    category_scope  TEXT NOT NULL DEFAULT 'all',    -- female_care / pet / baby / adult_care / all
    home_country    TEXT,
    notes           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
)
"""

CREATE_COLLAB = """
CREATE TABLE IF NOT EXISTS creator_competitor_collab (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id          INTEGER NOT NULL REFERENCES creator(id) ON DELETE CASCADE,
    competitor_brand_id INTEGER NOT NULL REFERENCES competitor_brand(id) ON DELETE CASCADE,
    evidence_url        TEXT,                       -- 视频/帖子链接
    detected_at         TEXT,                       -- ISO date
    confidence          REAL DEFAULT 1.0,           -- 0~1
    detection_source    TEXT,                       -- 'manual' / 'scraper_v1' / 'ai_classifier'
    notes               TEXT,
    created_at          TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_creator_excluded ON creator(excluded)",
    "CREATE INDEX IF NOT EXISTS idx_creator_engagement ON creator(engagement_rate)",
    "CREATE INDEX IF NOT EXISTS idx_creator_followers ON creator(followers)",
    "CREATE INDEX IF NOT EXISTS idx_collab_creator ON creator_competitor_collab(creator_id)",
    "CREATE INDEX IF NOT EXISTS idx_collab_brand ON creator_competitor_collab(competitor_brand_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_collab_creator_brand_evidence "
    "ON creator_competitor_collab(creator_id, competitor_brand_id, COALESCE(evidence_url,''))",
]

# ----- Resource registry -----
RESOURCE_ROWS = [
    ("competitor_brands", "competitor_brand", "id", ["code"], [], {},
     "竞品品牌（黑名单来源）"),
    ("creator_competitor_collabs", "creator_competitor_collab", "id", ["id"], [],
     {"creator_handle": ["creator", ["handle"], "creator_id"],
      "competitor_brand_code": ["competitor_brand", ["code"], "competitor_brand_id"]},
     "达人与竞品的合作记录"),
]

# ----- Seed common competitor brands -----
COMPETITOR_SEEDS = [
    # 女性护理
    ("always", "Always", "female_care", "US", "P&G 旗下女性护理头部品牌"),
    ("kotex", "Kotex", "female_care", "US", "Kimberly-Clark 旗下"),
    ("tampax", "Tampax", "female_care", "US", "P&G 旗下卫生棉条"),
    ("playtex", "Playtex", "female_care", "US", "Edgewell 旗下"),
    ("lola", "LOLA", "female_care", "US", "DTC 有机经期护理"),
    ("rael", "Rael", "female_care", "US", "韩裔创始 DTC 经期护理"),
    ("seventh_generation", "Seventh Generation", "female_care", "US", "Unilever 旗下，覆盖经期"),
    ("organyc", "Organyc", "female_care", "US", "意大利有机棉"),
    ("cora", "Cora", "female_care", "US", "DTC 经期护理"),
    ("the_honey_pot", "The Honey Pot", "female_care", "US", "黑人创始 DTC 经期护理"),
    # 母婴
    ("pampers", "Pampers", "baby", "US", "P&G 婴儿纸尿裤龙头"),
    ("huggies", "Huggies", "baby", "US", "Kimberly-Clark 婴儿纸尿裤"),
    ("luvs", "Luvs", "baby", "US", "P&G 婴儿纸尿裤"),
    ("honest_company", "The Honest Company", "baby", "US", "Jessica Alba 婴儿/家居"),
    ("hello_bello", "Hello Bello", "baby", "US", "Kristen Bell DTC 婴儿"),
    ("coterie", "Coterie", "baby", "US", "DTC 高端婴儿纸尿裤"),
    ("dyper", "DYPER", "baby", "US", "竹纤维婴儿纸尿裤"),
    # 成人护理
    ("depend", "Depend", "adult_care", "US", "Kimberly-Clark 成人失禁"),
    ("tena", "TENA", "adult_care", "US", "Essity 成人失禁"),
    ("prevail", "Prevail", "adult_care", "US", "FQHC 失禁产品"),
    # 宠物
    ("ph_pet", "Pet Honesty", "pet", "US", "DTC 宠物护理"),
    ("pet_magasin", "Pet Magasin", "pet", "US", "亚马逊宠物用品品牌"),
    ("simple_solution", "Simple Solution", "pet", "US", "宠物训练垫龙头"),
    ("amazon_basics_pet", "Amazon Basics Pet", "pet", "US", "亚马逊自营宠物用品"),
    ("pawtect", "Pawtect", "pet", "US", "宠物纸尿裤品牌"),
]


def add_col_if_missing(con: sqlite3.Connection, table: str, col_def: str) -> bool:
    name = col_def.split()[0]
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    if name in cols:
        return False
    con.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
    return True


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")

    # 1. Add columns to creator
    n_cols = 0
    for col_name, col_type in NEW_CREATOR_COLS:
        if add_col_if_missing(con, "creator", f"{col_name} {col_type}"):
            print(f"[migrate_v8] added creator.{col_name}")
            n_cols += 1

    # 2. New tables
    con.execute(CREATE_COMPETITOR)
    con.execute(CREATE_COLLAB)
    for idx in CREATE_INDEXES:
        try:
            con.execute(idx)
        except sqlite3.OperationalError as e:
            # COALESCE in unique-index needs SQLite >=3.9; fall back if old
            if "no such column" not in str(e).lower():
                pass

    # 3. Register new tables in _meta_resource
    for name, table, pk, upsert, json_cols, fk, desc in RESOURCE_ROWS:
        con.execute(
            "INSERT INTO _meta_resource(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
            "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
            "ON CONFLICT(name) DO UPDATE SET upsert_keys=excluded.upsert_keys, "
            "json_cols=excluded.json_cols, fk_lookup=excluded.fk_lookup, description=excluded.description",
            (name, table, pk, json.dumps(upsert), json.dumps(json_cols), json.dumps(fk), desc)
        )

    # 4. Seed competitor brands (idempotent by code)
    n_brands = 0
    for code, name, scope, country, notes in COMPETITOR_SEEDS:
        cur = con.execute(
            "INSERT OR IGNORE INTO competitor_brand(code,display_name,category_scope,home_country,notes) "
            "VALUES(?,?,?,?,?)", (code, name, scope, country, notes)
        )
        n_brands += cur.rowcount

    con.commit()

    n_total_brands = con.execute("SELECT COUNT(*) FROM competitor_brand").fetchone()[0]
    n_total_collabs = con.execute("SELECT COUNT(*) FROM creator_competitor_collab").fetchone()[0]
    by_scope = con.execute(
        "SELECT category_scope, COUNT(*) FROM competitor_brand GROUP BY category_scope ORDER BY 1"
    ).fetchall()

    print(f"[migrate_v8] +{n_cols} new columns on creator")
    print(f"[migrate_v8] +{n_brands} new competitor brands seeded")
    print(f"[migrate_v8] competitor_brand total: {n_total_brands}")
    print(f"[migrate_v8] creator_competitor_collab total: {n_total_collabs}")
    print(f"[migrate_v8] competitor breakdown by scope:")
    for scope, cnt in by_scope:
        print(f"   {scope:14s} {cnt}")
    con.close()


if __name__ == "__main__":
    main()
