"""
Create an empty X9 creator SQLite database with the same schema as the
current local desktop system.

Usage on the remote machine:

    python create_x9_creator_database.py --db ./creators.sqlite

The script is safe to run repeatedly. It creates missing tables/indexes and
adds the current_status column to older creator databases. It does not migrate
or copy any creator data.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


CURRENT_STATUS_VALUES = ("待建联", "已建联", "待回复", "视频已发布", "已寄样")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS creators (
    id VARCHAR(120) NOT NULL,
    platform VARCHAR(40) NOT NULL,
    handle VARCHAR(200) NOT NULL,
    display_name VARCHAR(300),
    profile_url TEXT,
    bio TEXT,
    followers_raw VARCHAR(40),
    followers_count INTEGER,
    email VARCHAR(320),
    has_email INTEGER NOT NULL DEFAULT 0,
    external_links_json TEXT,
    source_video_url TEXT,
    source_video_title TEXT,
    source_video_description TEXT,
    search_keyword VARCHAR(300),
    collected_at DATETIME,
    last_seen_at DATETIME,
    priority_score INTEGER NOT NULL DEFAULT 0,
    fit_level VARCHAR(8),
    priority_level VARCHAR(8),
    queue_type VARCHAR(60),
    primary_product_category VARCHAR(60),
    primary_product_fit_score INTEGER NOT NULL DEFAULT 0,
    feminine_care_fit INTEGER NOT NULL DEFAULT 0,
    pet_care_fit INTEGER NOT NULL DEFAULT 0,
    home_care_fit INTEGER NOT NULL DEFAULT 0,
    adult_care_fit INTEGER NOT NULL DEFAULT 0,
    mom_baby_fit INTEGER NOT NULL DEFAULT 0,
    health_mask_fit INTEGER NOT NULL DEFAULT 0,
    data_quality_score INTEGER NOT NULL DEFAULT 0,
    contactability_score INTEGER NOT NULL DEFAULT 0,
    content_format_score INTEGER NOT NULL DEFAULT 0,
    commercial_value_score INTEGER NOT NULL DEFAULT 0,
    follower_scale_score INTEGER NOT NULL DEFAULT 0,
    audience_fit_score INTEGER NOT NULL DEFAULT 0,
    recommendation_status VARCHAR(60),
    current_status VARCHAR(80),
    store_assigned VARCHAR(120),
    owner_bd VARCHAR(120),
    recommended_product_type VARCHAR(60),
    recommended_collab_type VARCHAR(60),
    outreach_priority VARCHAR(8),
    recommendation_score INTEGER NOT NULL DEFAULT 0,
    recommendation_reason TEXT,
    risk_summary TEXT,
    next_action TEXT,
    review_required INTEGER NOT NULL DEFAULT 0,
    review_status VARCHAR(40),
    notes TEXT,
    fit_evidence_source_json TEXT,
    matched_keywords_json TEXT,
    evidence_strength VARCHAR(20),
    evidence_text_json TEXT,
    risk_tags_json TEXT,
    positive_tags_json TEXT,
    content_format_status VARCHAR(40),
    score_version VARCHAR(40),
    tag_version VARCHAR(40),
    rec_version VARCHAR(40),
    scored_at DATETIME,
    tagged_at DATETIME,
    recommended_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_creator_platform_handle UNIQUE (platform, handle)
);

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
CREATE INDEX IF NOT EXISTS ix_creators_platform ON creators (platform);
CREATE INDEX IF NOT EXISTS ix_creators_handle ON creators (handle);
CREATE INDEX IF NOT EXISTS ix_creators_followers_count ON creators (followers_count);
CREATE INDEX IF NOT EXISTS ix_creators_email ON creators (email);
CREATE INDEX IF NOT EXISTS ix_creators_has_email ON creators (has_email);
CREATE INDEX IF NOT EXISTS ix_creators_search_keyword ON creators (search_keyword);
CREATE INDEX IF NOT EXISTS ix_creators_collected_at ON creators (collected_at);
CREATE INDEX IF NOT EXISTS ix_creators_priority_score ON creators (priority_score);
CREATE INDEX IF NOT EXISTS ix_creators_fit_level ON creators (fit_level);
CREATE INDEX IF NOT EXISTS ix_creators_priority_level ON creators (priority_level);
CREATE INDEX IF NOT EXISTS ix_creators_queue_type ON creators (queue_type);
CREATE INDEX IF NOT EXISTS ix_creators_primary_product_category ON creators (primary_product_category);
CREATE INDEX IF NOT EXISTS ix_creators_recommendation_status ON creators (recommendation_status);
CREATE INDEX IF NOT EXISTS ix_creators_current_status ON creators (current_status);
CREATE INDEX IF NOT EXISTS ix_creators_store_assigned ON creators (store_assigned);
CREATE INDEX IF NOT EXISTS ix_creators_owner_bd ON creators (owner_bd);
CREATE INDEX IF NOT EXISTS ix_creators_recommended_product_type ON creators (recommended_product_type);
CREATE INDEX IF NOT EXISTS ix_creators_recommended_collab_type ON creators (recommended_collab_type);
CREATE INDEX IF NOT EXISTS ix_creators_outreach_priority ON creators (outreach_priority);
CREATE INDEX IF NOT EXISTS ix_creators_recommendation_score ON creators (recommendation_score);
CREATE INDEX IF NOT EXISTS ix_creators_review_required ON creators (review_required);
CREATE INDEX IF NOT EXISTS ix_creators_review_status ON creators (review_status);

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


def create_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        ensure_legacy_columns(conn)
        conn.executescript(INDEX_SQL)
        seed_tag_definitions(conn)
        conn.commit()


def ensure_legacy_columns(conn: sqlite3.Connection) -> None:
    creator_columns = {row[1] for row in conn.execute("PRAGMA table_info(creators)")}
    if "current_status" not in creator_columns:
        conn.execute("ALTER TABLE creators ADD COLUMN current_status VARCHAR(80)")


def seed_tag_definitions(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR IGNORE INTO tag_definitions (tag_code, tag_name, tag_type, is_active)
        VALUES (?, ?, ?, 1)
        """,
        [
            (code, code.replace("_", " ").title(), tag_type)
            for code, tag_type in TAG_DEFINITIONS
        ],
    )


def table_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    out = []
    for (name,) in rows:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        out.append((name, count))
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the X9 creator SQLite database schema.")
    parser.add_argument("--db", default="./creators.sqlite", help="Target SQLite database path.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the target database first. Use only when you want an empty fresh database.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    if args.reset and db_path.exists():
        db_path.unlink()

    create_database(db_path)

    with sqlite3.connect(db_path) as conn:
        counts = table_counts(conn)
    print(f"X9 creator database schema is ready: {db_path}")
    print("Current status values:", ", ".join(CURRENT_STATUS_VALUES))
    print("Tables:")
    for table, count in counts:
        print(f"  - {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
