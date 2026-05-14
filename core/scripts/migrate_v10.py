"""Schema migration v10: 实时热搜抓取支撑设施（任务 2.2.2 升级版）

新增：
- keyword_snapshot 表：每次抓取写一行历史快照，做趋势曲线 / 异动检测
- scrape_run 表：每次抓取任务的元数据（开始/结束/数量/错误）
- 触发器 trg_keyword_snapshot：tk_hot_keyword INSERT/UPDATE 时自动写一条 snapshot
- 触发器 trg_keyword_relevance：插入新关键词时自动按 keyword 文本启发式匹配 category_hint
  （仅当原 category_hint 为 NULL 时填，已有值不覆盖）
- 注册 2 张新表为通用 resource

Idempotent.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"


CREATE_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS keyword_snapshot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id      INTEGER NOT NULL REFERENCES tk_hot_keyword(id) ON DELETE CASCADE,
    captured_at     TEXT NOT NULL DEFAULT (datetime('now')),
    search_volume   INTEGER,
    growth_rate     REAL,
    rank_position   INTEGER,
    scrape_run_id   INTEGER REFERENCES scrape_run(id) ON DELETE SET NULL
)
"""

CREATE_SCRAPE_RUN = """
CREATE TABLE IF NOT EXISTS scrape_run (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at     TEXT,
    source          TEXT NOT NULL,                  -- 'tiktok_creator_center' / 'tt_search' / 'manual_api' / ...
    region          TEXT DEFAULT 'US',
    triggered_by    TEXT,                           -- 'cron' / 'manual' / 'webhook'
    operator        TEXT,                           -- username if manual
    n_added         INTEGER DEFAULT 0,
    n_updated       INTEGER DEFAULT 0,
    n_errors        INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'running',          -- running / done / failed
    error_message   TEXT,
    notes           TEXT
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_snap_keyword ON keyword_snapshot(keyword_id, captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_snap_recent ON keyword_snapshot(captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_run_status ON scrape_run(status, started_at)",
]

# Trigger: 每次 tk_hot_keyword 被 INSERT 或 UPDATE（搜索量/增长率/排名 任一变化）时
# 自动写一条 snapshot，便于做时序曲线
CREATE_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS trg_kw_snapshot_insert
AFTER INSERT ON tk_hot_keyword FOR EACH ROW
BEGIN
    INSERT INTO keyword_snapshot(keyword_id, search_volume, growth_rate, rank_position)
    VALUES (NEW.id, NEW.search_volume, NEW.growth_rate, NEW.rank_position);
END
"""

CREATE_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS trg_kw_snapshot_update
AFTER UPDATE ON tk_hot_keyword FOR EACH ROW
WHEN OLD.search_volume IS NOT NEW.search_volume
  OR OLD.growth_rate IS NOT NEW.growth_rate
  OR OLD.rank_position IS NOT NEW.rank_position
BEGIN
    INSERT INTO keyword_snapshot(keyword_id, search_volume, growth_rate, rank_position)
    VALUES (NEW.id, NEW.search_volume, NEW.growth_rate, NEW.rank_position);
END
"""

# 启发式 category_hint 自动填补：AFTER INSERT，仅当原值为空时填
# (BEFORE INSERT 不行 — SQLite 里 NEW.id 在插入前不存在，UPDATE WHERE id=NEW.id 匹配不到任何行)
DROP_OLD_CATEGORY_TRIGGER = "DROP TRIGGER IF EXISTS trg_kw_auto_category"
CREATE_TRIGGER_CATEGORY = """
CREATE TRIGGER IF NOT EXISTS trg_kw_auto_category
AFTER INSERT ON tk_hot_keyword FOR EACH ROW
WHEN NEW.category_hint IS NULL OR NEW.category_hint = ''
BEGIN
    UPDATE tk_hot_keyword SET category_hint = (
        CASE
            WHEN LOWER(NEW.keyword) LIKE '%period%' OR LOWER(NEW.keyword) LIKE '%pad%'
              OR LOWER(NEW.keyword) LIKE '%tampon%' OR LOWER(NEW.keyword) LIKE '%liner%'
              OR LOWER(NEW.keyword) LIKE '%feminine%' OR LOWER(NEW.keyword) LIKE '%menstrual%'
              THEN 'female_care'
            WHEN LOWER(NEW.keyword) LIKE '%dog%' OR LOWER(NEW.keyword) LIKE '%puppy%'
              OR LOWER(NEW.keyword) LIKE '%cat %' OR LOWER(NEW.keyword) LIKE '% cat'
              OR LOWER(NEW.keyword) LIKE '%pet%'
              THEN 'pet'
            WHEN LOWER(NEW.keyword) LIKE '%baby%' OR LOWER(NEW.keyword) LIKE '%newborn%'
              OR LOWER(NEW.keyword) LIKE '%toddler%' OR LOWER(NEW.keyword) LIKE '%nursing%'
              THEN 'baby'
            WHEN LOWER(NEW.keyword) LIKE '%adult%' OR LOWER(NEW.keyword) LIKE '%incontinence%'
              OR LOWER(NEW.keyword) LIKE '%bladder%' OR LOWER(NEW.keyword) LIKE '%postpartum%'
              THEN 'adult_care'
            WHEN LOWER(NEW.keyword) LIKE '%underpad%' OR LOWER(NEW.keyword) LIKE '%bed pad%'
              OR LOWER(NEW.keyword) LIKE '%mattress%' OR LOWER(NEW.keyword) LIKE '%training pad%'
              THEN 'home_care'
            WHEN LOWER(NEW.keyword) LIKE '%mask%' OR LOWER(NEW.keyword) LIKE '%kn95%'
              THEN 'mask'
            ELSE NULL
        END
    ) WHERE id = NEW.id AND (category_hint IS NULL OR category_hint = '');
END
"""

RESOURCE_ROWS = [
    ("keyword_snapshots", "keyword_snapshot", "id", ["id"], [], {},
     "热搜关键词历史快照（趋势/曲线用）"),
    ("scrape_runs", "scrape_run", "id", ["id"], [], {},
     "热搜抓取任务走计"),
]


def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys=ON")

    # 1. Create tables (in correct order for FK)
    con.execute(CREATE_SCRAPE_RUN)
    con.execute(CREATE_SNAPSHOT)
    for idx in CREATE_INDEXES:
        con.execute(idx)

    # 2. Triggers — drop old category trigger first if it exists (was BEFORE INSERT, broken)
    con.execute(DROP_OLD_CATEGORY_TRIGGER)
    for tg in [CREATE_TRIGGER_INSERT, CREATE_TRIGGER_UPDATE, CREATE_TRIGGER_CATEGORY]:
        con.execute(tg)

    # 3. Register resources
    for name, table, pk, upsert, json_cols, fk, desc in RESOURCE_ROWS:
        con.execute(
            "INSERT INTO _meta_resource(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
            "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
            "ON CONFLICT(name) DO UPDATE SET upsert_keys=excluded.upsert_keys, "
            "json_cols=excluded.json_cols, description=excluded.description",
            (name, table, pk, json.dumps(upsert), json.dumps(json_cols), json.dumps(fk), desc)
        )

    # 4. Backfill — give existing keywords ONE seed snapshot so charts have a starting point
    n_back = con.execute("""
        INSERT INTO keyword_snapshot(keyword_id, captured_at, search_volume, growth_rate, rank_position)
        SELECT id, COALESCE(updated_at, datetime('now')), search_volume, growth_rate, rank_position
        FROM tk_hot_keyword
        WHERE id NOT IN (SELECT DISTINCT keyword_id FROM keyword_snapshot)
    """).rowcount
    con.commit()

    n_total_snap = con.execute("SELECT COUNT(*) FROM keyword_snapshot").fetchone()[0]
    n_total_runs = con.execute("SELECT COUNT(*) FROM scrape_run").fetchone()[0]
    print(f"[migrate_v10] tables ready, 3 triggers installed")
    print(f"[migrate_v10] backfilled +{n_back} initial snapshots (one per existing keyword)")
    print(f"[migrate_v10] keyword_snapshot total: {n_total_snap}")
    print(f"[migrate_v10] scrape_run total: {n_total_runs}")
    con.close()


if __name__ == "__main__":
    main()
