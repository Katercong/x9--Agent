"""migrate_v18: UI support tables for the new React management portal.

Adds five tables (all additive, all idempotent):
  - department: company / department hierarchy (3-role admin structure)
  - api_metric: per-endpoint call count / avg latency / error rate
  - llm_token_usage: daily LLM token consumption per provider/feature
  - business_metric_daily: cached daily KPI rollups for fast dashboard loads
  - notification: app-level notifications (sidebar bell icon)

Plus:
  - department_id FK column on `creator` and `staff` (nullable, additive)
  - All 5 new tables registered in _meta_resource so they appear in /api/v1/data/*

Idempotent: every CREATE uses IF NOT EXISTS, every ALTER is guarded by a
column-existence check.

Usage:
  py core/scripts/migrate_v18_ui_support.py
"""
from __future__ import annotations
import sqlite3
import json
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "database.db"


def column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def add_column_if_missing(con: sqlite3.Connection, table: str, column_def: str, column_name: str) -> str:
    if column_exists(con, table, column_name):
        return "exists"
    con.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    return "added"


def register_resource(con: sqlite3.Connection, name: str, table: str, pk: str, *, desc: str, writable: bool = True) -> None:
    """Register a table as a generic CRUD resource so it appears in /api/v1/data/{name}."""
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_meta_resource'")
    if not cur.fetchone():
        # _meta_resource doesn't exist (older DB) — skip silently
        return
    con.execute("""
        INSERT OR IGNORE INTO _meta_resource(
            name, table_name, pk, upsert_keys, json_cols, fk_lookup,
            description, is_dynamic, writable
        ) VALUES (?, ?, ?, '[]', '[]', '{}', ?, 1, ?)
    """, (name, table, pk, desc, 1 if writable else 0))


def main() -> None:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys = ON")
    results: list[tuple[str, str]] = []

    try:
        # ---------- 1. department ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS department (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT UNIQUE NOT NULL,        -- cross_border / foreign_trade / sourcing
                name_zh     TEXT NOT NULL,
                name_en     TEXT,
                parent_id   INTEGER REFERENCES department(id),
                manager     TEXT,                         -- 主管 staff.name
                description TEXT,
                active      INTEGER NOT NULL DEFAULT 1,
                sort_order  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_department_parent ON department(parent_id)")
        results.append(("department", "table+index ready"))

        # Seed default departments (idempotent — only insert if empty)
        existing = con.execute("SELECT COUNT(*) FROM department").fetchone()[0]
        if existing == 0:
            seeds = [
                ("cross_border", "跨境数据库部门", "Cross-Border", None, "Mercy", "跨境电商达人建联中台主部门"),
                ("foreign_trade", "外贸部", "Foreign Trade", None, None, "传统外贸业务部门"),
                ("sourcing", "选品部", "Sourcing", None, None, "产品研发与选品"),
                ("operations", "运营部", "Operations", None, None, "日常运营 + 客服"),
            ]
            con.executemany("""
                INSERT INTO department(code, name_zh, name_en, parent_id, manager, description)
                VALUES (?, ?, ?, ?, ?, ?)
            """, seeds)
            results.append(("department", f"seeded {len(seeds)} rows"))

        # ---------- 2. api_metric ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS api_metric (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint        TEXT NOT NULL,            -- '/api/v1/data/creators'
                method          TEXT NOT NULL DEFAULT 'GET',
                day             TEXT NOT NULL,            -- YYYY-MM-DD
                hour            INTEGER NOT NULL DEFAULT 0,
                call_count      INTEGER NOT NULL DEFAULT 0,
                error_count     INTEGER NOT NULL DEFAULT 0,
                total_ms        INTEGER NOT NULL DEFAULT 0,  -- sum of latencies (for avg计算)
                p99_ms          INTEGER,
                last_called_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(endpoint, method, day, hour)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_api_metric_day ON api_metric(day)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_api_metric_endpoint ON api_metric(endpoint)")
        results.append(("api_metric", "table+index ready"))

        # ---------- 3. llm_token_usage ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS llm_token_usage (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_code    TEXT NOT NULL,           -- 'anthropic' / 'openai' / ...
                model            TEXT,                    -- 'claude-opus-4-7'
                feature          TEXT,                    -- 'agent' / 'outreach_script' / ...
                day              TEXT NOT NULL,           -- YYYY-MM-DD
                input_tokens     INTEGER NOT NULL DEFAULT 0,
                output_tokens    INTEGER NOT NULL DEFAULT 0,
                call_count       INTEGER NOT NULL DEFAULT 0,
                error_count      INTEGER NOT NULL DEFAULT 0,
                total_cost_usd   REAL DEFAULT 0,
                last_used_at     TEXT DEFAULT (datetime('now')),
                UNIQUE(provider_code, model, feature, day)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_day ON llm_token_usage(day)")
        results.append(("llm_token_usage", "table+index ready"))

        # ---------- 4. business_metric_daily ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS business_metric_daily (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                day                 TEXT NOT NULL,           -- YYYY-MM-DD
                scope_kind          TEXT NOT NULL,           -- 'company' / 'department' / 'staff'
                scope_id            TEXT,                    -- department.code / staff.name / NULL=全公司
                creators_total      INTEGER DEFAULT 0,
                creators_new        INTEGER DEFAULT 0,
                creators_active     INTEGER DEFAULT 0,
                creators_prospect   INTEGER DEFAULT 0,
                outreach_total      INTEGER DEFAULT 0,
                outreach_new        INTEGER DEFAULT 0,
                contacted_count     INTEGER DEFAULT 0,
                confirmed_count     INTEGER DEFAULT 0,
                sample_shipped      INTEGER DEFAULT 0,
                video_published     INTEGER DEFAULT 0,
                ad_running          INTEGER DEFAULT 0,
                conversion_rate     REAL DEFAULT 0,          -- 转化率
                avg_response_hours  REAL,
                gmv_30d_usd         REAL DEFAULT 0,
                computed_at         TEXT DEFAULT (datetime('now')),
                UNIQUE(day, scope_kind, scope_id)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_biz_metric_day ON business_metric_daily(day)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_biz_metric_scope ON business_metric_daily(scope_kind, scope_id)")
        results.append(("business_metric_daily", "table+index ready"))

        # ---------- 5. notification ----------
        con.execute("""
            CREATE TABLE IF NOT EXISTS notification (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient     TEXT NOT NULL,            -- user 'zhang' / 'liao' / 'mercy' / '*'=广播
                title         TEXT NOT NULL,
                body          TEXT,
                level         TEXT NOT NULL DEFAULT 'info',  -- info/success/warning/error
                category      TEXT,                      -- system/outreach/review/import/etc
                link_url      TEXT,                      -- 前端可跳转的内部路径
                related_table TEXT,                      -- 关联资源表名 (creators/outreach...)
                related_id    INTEGER,
                read_at       TEXT,                      -- NULL=未读
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_notification_recipient ON notification(recipient)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_notification_unread ON notification(recipient, read_at)")
        results.append(("notification", "table+index ready"))

        # ---------- 6. department_id columns on creator/staff/outreach ----------
        for table in ("creator", "staff", "outreach"):
            cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not cur.fetchone():
                results.append((f"{table}.department_id", "table missing — skipped"))
                continue
            res = add_column_if_missing(con, table, "department_id INTEGER REFERENCES department(id)", "department_id")
            results.append((f"{table}.department_id", res))

        # Index on department_id for fast filtering
        con.execute("CREATE INDEX IF NOT EXISTS idx_creator_dept ON creator(department_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_outreach_dept ON outreach(department_id)")

        # Set default department_id = cross_border for existing rows (one-time backfill)
        default_dept = con.execute("SELECT id FROM department WHERE code='cross_border'").fetchone()
        if default_dept:
            did = default_dept[0]
            for table in ("creator", "staff", "outreach"):
                cur = con.execute(f"UPDATE {table} SET department_id = ? WHERE department_id IS NULL", (did,))
                if cur.rowcount > 0:
                    results.append((f"{table} backfill", f"set department_id={did} on {cur.rowcount} rows"))

        # ---------- 7. Register new resources for /api/v1/data/* ----------
        register_resource(con, "departments", "department", "id", desc="组织部门(公司/部门/小组 层级)", writable=True)
        register_resource(con, "api_metrics", "api_metric", "id", desc="API 调用统计(端点 × 日 × 小时)", writable=False)
        register_resource(con, "llm_token_usages", "llm_token_usage", "id", desc="LLM Token 用量(Provider × 模型 × Feature × 日)", writable=False)
        register_resource(con, "business_metrics_daily", "business_metric_daily", "id", desc="业务 KPI 日快照(公司/部门/BD 维度)", writable=False)
        register_resource(con, "notifications", "notification", "id", desc="应用内通知(侧栏铃铛)", writable=True)
        results.append(("_meta_resource", "5 resources registered"))

        # ---------- 8. Seed sample data for immediate UI verification ----------
        # 仅在表为空时插入示例,避免污染真实数据
        if con.execute("SELECT COUNT(*) FROM notification").fetchone()[0] == 0:
            con.execute("""
                INSERT INTO notification(recipient, title, body, level, category, link_url)
                VALUES
                ('*', '系统已升级到 v2.1.0', '本次升级新增 5 张支撑表:departments / api_metrics / llm_token_usages / business_metrics_daily / notifications。', 'info', 'system', '/a/api-stats'),
                ('*', '前端管理端切换完成', 'React 重构版管理端已上线,默认 /web-preview/。老版 / 仍可访问。', 'success', 'system', '/web-preview/'),
                ('Mercy', '今日待联系 5 个达人', '/d/dashboard 查看完整列表', 'info', 'outreach', '/d/dashboard')
            """)
            results.append(("notification", "seeded 3 sample rows"))

        con.commit()
        print("[migrate_v18] complete:")
        for k, v in results:
            print(f"  {k:30s} {v}")

    except Exception as e:
        con.rollback()
        print(f"[migrate_v18] FAILED: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()
