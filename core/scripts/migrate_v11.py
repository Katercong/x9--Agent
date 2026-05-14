"""migrate_v11 — 廖爬虫数据接收层（lead 池支持表）

⚠️ v3.8.1 调整：廖另建了 `tk_creators` 表作为 lead 池，本脚本不再创建 `creators` 表。
   creator_leads URL slug 由 migrate_v12.py 撤销。
   tk_creators 是廖通过 v3.8.0 解锁的 DDL 端点自助建的，不在本脚本管理范围。

并行新增 8 张支持表（v11 原本是 9 张表 + creators，现在只剩支持表），不动现有 creator/outreach 主表。
运行多次幂等。run.bat 每次启动都会跑一遍。

新增表语义：
  raw_observations      — 每次抓取的原始 JSON 留底
  tag_definitions       — 标签字典（80 个 seed）
  creator_tags          — creator × tag 多对多
  creator_recommendations — AI 推荐结果（多版本）
  review_tasks          — 人工审核队列
  system_logs           — 廖端日志
  extension_sessions    — Chrome 扩展心跳
  extension_commands    — 给扩展下的命令队列
  extension_run_progress — 扩展运行进度（每个 worker 一条）

后续 ETL：creator_leads（lead 池）→ creator（已确认主表）由专门的脚本做。
本迁移只负责"接收层"，不涉及任何主表数据。
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "database.db"

SCHEMA_SQL = """
-- v3.8.1: creators 表已撤出（廖用 tk_creators 自建）。下面是支持表。

CREATE TABLE IF NOT EXISTS raw_observations (
    id VARCHAR(120) NOT NULL,
    platform VARCHAR(40) NOT NULL,
    source VARCHAR(80) NOT NULL,
    worker_id VARCHAR(80),
    account_id VARCHAR(80),
    search_keyword VARCHAR(300),
    raw_json TEXT NOT NULL,
    content_hash VARCHAR(80) NOT NULL,
    collected_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS tag_definitions (
    tag_code VARCHAR(120) NOT NULL,
    tag_name VARCHAR(200),
    tag_type VARCHAR(40) NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (tag_code)
);

CREATE TABLE IF NOT EXISTS creator_tags (
    id VARCHAR(120) NOT NULL,
    creator_id VARCHAR(120) NOT NULL,
    tag_code VARCHAR(120) NOT NULL,
    tag_type VARCHAR(40) NOT NULL,
    source VARCHAR(80),
    confidence FLOAT NOT NULL DEFAULT 1.0,
    evidence_text TEXT,
    matched_keywords_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_creator_tag UNIQUE (creator_id, tag_code)
);

CREATE TABLE IF NOT EXISTS creator_recommendations (
    id VARCHAR(120) NOT NULL,
    creator_id VARCHAR(120) NOT NULL,
    recommendation_status VARCHAR(60),
    recommended_product_type VARCHAR(60),
    recommended_collab_type VARCHAR(60),
    outreach_priority VARCHAR(8),
    recommendation_score INTEGER NOT NULL DEFAULT 0,
    recommendation_reason TEXT,
    risk_summary TEXT,
    next_action TEXT,
    rec_version VARCHAR(40),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS review_tasks (
    id VARCHAR(120) NOT NULL,
    creator_id VARCHAR(120) NOT NULL,
    task_type VARCHAR(60) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    risk_tags_json TEXT,
    reason TEXT,
    reviewer_notes TEXT,
    assigned_staff_id VARCHAR(80),
    review_result VARCHAR(120),
    reviewed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS system_logs (
    id VARCHAR(120) NOT NULL,
    level VARCHAR(10) NOT NULL DEFAULT 'INFO',
    module VARCHAR(80),
    message TEXT NOT NULL,
    details_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS extension_sessions (
    id VARCHAR(120) NOT NULL,
    extension_id VARCHAR(120) NOT NULL,
    extension_version VARCHAR(40),
    worker_id VARCHAR(80) NOT NULL,
    account_id VARCHAR(80),
    browser_profile VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'online',
    current_url TEXT,
    page_type VARCHAR(40),
    tiktok_page_status VARCHAR(40),
    tiktok_login_status VARCHAR(40),
    active_tab_title TEXT,
    last_heartbeat_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS extension_commands (
    id VARCHAR(120) NOT NULL,
    worker_id VARCHAR(80) NOT NULL,
    command_type VARCHAR(60) NOT NULL,
    payload_json TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    result_json TEXT,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    claimed_at DATETIME,
    completed_at DATETIME,
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS extension_run_progress (
    id VARCHAR(120) NOT NULL,
    worker_id VARCHAR(80) NOT NULL,
    keyword VARCHAR(300),
    step VARCHAR(40) NOT NULL DEFAULT 'idle',
    running INTEGER NOT NULL DEFAULT 0,
    stop_requested INTEGER NOT NULL DEFAULT 0,
    started_at DATETIME,
    finished_at DATETIME,
    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    profiles_visited INTEGER NOT NULL DEFAULT 0,
    profiles_remaining INTEGER NOT NULL DEFAULT 0,
    queue_size INTEGER NOT NULL DEFAULT 0,
    leads_saved INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    scrolls_done INTEGER NOT NULL DEFAULT 0,
    rest_breaks INTEGER NOT NULL DEFAULT 0,
    current_handle VARCHAR(200),
    current_action TEXT,
    last_error TEXT,
    settings_json TEXT,
    queue_json TEXT,
    recent_leads_json TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_extension_run_progress_worker UNIQUE (worker_id)
);
"""

INDEX_SQL = """
-- v3.8.1: creators 索引也撤出
CREATE INDEX IF NOT EXISTS ix_raw_observations_platform ON raw_observations (platform);
CREATE INDEX IF NOT EXISTS ix_raw_observations_worker_id ON raw_observations (worker_id);
CREATE INDEX IF NOT EXISTS ix_raw_observations_account_id ON raw_observations (account_id);
CREATE INDEX IF NOT EXISTS ix_raw_observations_search_keyword ON raw_observations (search_keyword);
CREATE INDEX IF NOT EXISTS ix_raw_observations_content_hash ON raw_observations (content_hash);
CREATE INDEX IF NOT EXISTS ix_raw_observations_collected_at ON raw_observations (collected_at);
CREATE INDEX IF NOT EXISTS ix_raw_observations_created_at ON raw_observations (created_at);

CREATE INDEX IF NOT EXISTS ix_tag_definitions_tag_type ON tag_definitions (tag_type);
CREATE INDEX IF NOT EXISTS ix_tag_definitions_is_active ON tag_definitions (is_active);

CREATE INDEX IF NOT EXISTS ix_creator_tags_creator_id ON creator_tags (creator_id);
CREATE INDEX IF NOT EXISTS ix_creator_tags_tag_code ON creator_tags (tag_code);
CREATE INDEX IF NOT EXISTS ix_creator_tags_tag_type ON creator_tags (tag_type);

CREATE INDEX IF NOT EXISTS ix_creator_recommendations_creator_id ON creator_recommendations (creator_id);
CREATE INDEX IF NOT EXISTS ix_creator_recommendations_recommendation_status ON creator_recommendations (recommendation_status);
CREATE INDEX IF NOT EXISTS ix_creator_recommendations_recommended_product_type ON creator_recommendations (recommended_product_type);
CREATE INDEX IF NOT EXISTS ix_creator_recommendations_recommended_collab_type ON creator_recommendations (recommended_collab_type);
CREATE INDEX IF NOT EXISTS ix_creator_recommendations_outreach_priority ON creator_recommendations (outreach_priority);
CREATE INDEX IF NOT EXISTS ix_creator_recommendations_created_at ON creator_recommendations (created_at);

CREATE INDEX IF NOT EXISTS ix_review_tasks_creator_id ON review_tasks (creator_id);
CREATE INDEX IF NOT EXISTS ix_review_tasks_task_type ON review_tasks (task_type);
CREATE INDEX IF NOT EXISTS ix_review_tasks_status ON review_tasks (status);

CREATE INDEX IF NOT EXISTS ix_system_logs_level ON system_logs (level);
CREATE INDEX IF NOT EXISTS ix_system_logs_module ON system_logs (module);
CREATE INDEX IF NOT EXISTS ix_system_logs_created_at ON system_logs (created_at);

CREATE INDEX IF NOT EXISTS ix_extension_sessions_extension_id ON extension_sessions (extension_id);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_worker_id ON extension_sessions (worker_id);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_account_id ON extension_sessions (account_id);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_status ON extension_sessions (status);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_page_type ON extension_sessions (page_type);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_tiktok_login_status ON extension_sessions (tiktok_login_status);
CREATE INDEX IF NOT EXISTS ix_extension_sessions_last_heartbeat_at ON extension_sessions (last_heartbeat_at);

CREATE INDEX IF NOT EXISTS ix_extension_commands_worker_id ON extension_commands (worker_id);
CREATE INDEX IF NOT EXISTS ix_extension_commands_command_type ON extension_commands (command_type);
CREATE INDEX IF NOT EXISTS ix_extension_commands_status ON extension_commands (status);
CREATE INDEX IF NOT EXISTS ix_extension_commands_created_at ON extension_commands (created_at);

CREATE INDEX IF NOT EXISTS ix_extension_run_progress_worker_id ON extension_run_progress (worker_id);
CREATE INDEX IF NOT EXISTS ix_extension_run_progress_step ON extension_run_progress (step);
"""

TAG_DEFINITIONS = [
    *[(code, "risk") for code in [
        "search_keyword_only_match", "weak_category_evidence", "missing_email",
        "unknown_content_format", "low_product_fit", "macro_low_fit",
        "manual_review_required", "conflicting_category_signals",
    ]],
    *[(code, "positive") for code in [
        "has_email", "has_alt_contact", "high_followers", "medium_followers", "micro_creator",
        "strong_feminine_care_fit", "medium_feminine_care_fit",
        "high_commercial_value", "sample_collab_candidate",
        "affiliate_candidate", "brand_awareness_candidate",
        "strong_commerce_signal", "commerce_test_candidate",
        "repeat_target_tag_signal", "same_keyword_multi_video",
        "multi_keyword_discovery", "repeat_commerce_signal",
        "repeat_feminine_care_signal", "repeat_pet_care_signal",
        "repeat_home_care_signal", "repeat_adult_care_signal",
        "repeat_mom_baby_signal", "repeat_health_mask_signal",
    ]],
    *[(code, "product_category") for code in [
        "feminine_care", "pet_care", "home_care", "adult_care",
        "mom_baby", "health_mask", "general_lifestyle",
    ]],
    *[(code, "product_fit") for code in [
        "feminine_care_daily_liner", "period_care_pad", "sensitive_skin_care",
        "travel_hygiene_pack", "postpartum_mom_care", "teen_first_period_care",
        "wellness_self_care_bundle",
    ]],
    *[(code, "content_vertical") for code in [
        "period_education_creator", "women_wellness_creator",
        "beauty_lifestyle_creator", "skin_body_care_creator", "self_care_creator",
        "mom_creator", "postpartum_creator", "pet_creator", "dog_creator",
        "home_cleaning_creator", "caregiver_creator", "general_lifestyle_creator",
    ]],
    *[(code, "content_format") for code in [
        "ugc_creator", "review_style", "unboxing_style", "deal_finds_style",
        "routine_style", "educational_style", "problem_solution_style",
        "asmr_demo_style", "live_selling_style", "entertainment_style",
    ]],
    *[(code, "collaboration") for code in [
        "email_available", "email_missing", "email_suspect", "multiple_emails",
        "personal_email", "agency_email", "brand_domain_email",
        "collab_friendly", "sample_friendly", "high_cost_risk",
        "brand_awareness_only", "conversion_focused",
    ]],
]

# (resource_url_slug, table, pk, upsert_keys, json_cols, description)
# v3.8.1: creator_leads 已撤；廖用 tk_creators 自助建（v3.8.0 D-015 解锁的 DDL）
META_RESOURCES = [
    ("raw_observations", "raw_observations", "id",
     ["content_hash"],
     ["raw_json"],
     "每次抓取的原始 JSON 留底（按 content_hash 去重）"),
    ("tag_definitions", "tag_definitions", "tag_code",
     ["tag_code"],
     [],
     "标签字典（80 seed：risk/positive/product_category/product_fit/content_vertical/content_format/collaboration）"),
    ("creator_tags", "creator_tags", "id",
     ["creator_id", "tag_code"],
     ["matched_keywords_json"],
     "creator × tag 多对多（指向 creator_leads.id）"),
    ("creator_recommendations", "creator_recommendations", "id",
     ["id"],
     [],
     "AI 推荐结果（多版本，按 rec_version 区分）"),
    ("review_tasks", "review_tasks", "id",
     ["id"],
     ["risk_tags_json"],
     "人工审核队列"),
    ("system_logs", "system_logs", "id",
     ["id"],
     ["details_json"],
     "廖端日志（append-only）"),
    ("extension_sessions", "extension_sessions", "id",
     ["worker_id"],
     [],
     "Chrome 扩展心跳"),
    ("extension_commands", "extension_commands", "id",
     ["id"],
     ["payload_json", "result_json"],
     "给扩展下的命令队列"),
    ("extension_run_progress", "extension_run_progress", "id",
     ["worker_id"],
     ["settings_json", "queue_json", "recent_leads_json"],
     "扩展运行进度（每 worker 一条）"),
]


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        # v3.8.1: 不再处理 creators 表（已交给 migrate_v12 撤销）
        con.executescript(SCHEMA_SQL)
        con.executescript(INDEX_SQL)

        # seed tag_definitions
        seeded = 0
        cur = con.cursor()
        for code, tag_type in TAG_DEFINITIONS:
            cur.execute(
                "INSERT OR IGNORE INTO tag_definitions(tag_code, tag_name, tag_type, is_active) "
                "VALUES(?,?,?,1)",
                (code, code.replace("_", " ").title(), tag_type),
            )
            seeded += cur.rowcount

        # register all 10 resources into _meta_resource (idempotent UPSERT)
        for slug, table, pk, upsert_keys, json_cols, desc in META_RESOURCES:
            con.execute(
                "INSERT INTO _meta_resource(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
                "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
                "ON CONFLICT(name) DO UPDATE SET table_name=excluded.table_name, "
                "pk=excluded.pk, upsert_keys=excluded.upsert_keys, json_cols=excluded.json_cols, "
                "description=excluded.description",
                (slug, table, pk,
                 json.dumps(upsert_keys),
                 json.dumps(json_cols),
                 json.dumps({}),
                 desc),
            )

        con.commit()

        # report
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('raw_observations','tag_definitions','creator_tags',"
            "'creator_recommendations','review_tasks','system_logs','extension_sessions',"
            "'extension_commands','extension_run_progress') ORDER BY name"
        ).fetchall()
        print(f"[migrate_v11] {len(rows)} support tables present:")
        for (t,) in rows:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} rows")
        tag_n = con.execute("SELECT COUNT(*) FROM tag_definitions").fetchone()[0]
        print(f"[migrate_v11] tag_definitions seeded ({seeded} new this run, {tag_n} total)")
        meta_n = con.execute(
            "SELECT COUNT(*) FROM _meta_resource WHERE name IN "
            "('raw_observations','tag_definitions','creator_tags',"
            "'creator_recommendations','review_tasks','system_logs','extension_sessions',"
            "'extension_commands','extension_run_progress')"
        ).fetchone()[0]
        print(f"[migrate_v11] {meta_n}/9 resources registered in _meta_resource")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
