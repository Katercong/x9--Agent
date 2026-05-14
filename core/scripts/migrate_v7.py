"""Schema migration v7: 邀约话术生成器所需的 4 张表 + 业务配置落库。

新增表：
- app_config         系统级 KV 配置（outreach_policy / brand 信息 / 禁词等）
- brand_profile      品牌资料抽取结果
- outreach_example   历史话术 few-shot
- outbox             半自动触达队列（一行一条待发/已发记录）

并：
- 在 _meta_resource 注册新表为通用 CRUD resource
- 种入 v1 默认值（commission 20% / 1 包寄样 / 7 天物流 / 禁词清单 / 品牌定位 / pet_care 固定话术）

Idempotent.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"


# ============================================================
# Tables
# ============================================================
CREATE_APP_CONFIG = """
CREATE TABLE IF NOT EXISTS app_config (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    value_type  TEXT NOT NULL DEFAULT 'string'    -- string / number / json / boolean
                CHECK (value_type IN ('string','number','json','boolean')),
    category    TEXT,                              -- outreach / brand / system
    description TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
)
"""

CREATE_BRAND_PROFILE = """
CREATE TABLE IF NOT EXISTS brand_profile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    body_text       TEXT,
    source_path     TEXT,                              -- 来源文件
    category_scope  TEXT NOT NULL DEFAULT 'all',       -- all / female_care / pet / baby / adult_care / home_care
    language        TEXT NOT NULL DEFAULT 'en',
    is_active       INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER DEFAULT 0,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""

CREATE_OUTREACH_EXAMPLE = """
CREATE TABLE IF NOT EXISTS outreach_example (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_key    TEXT,                              -- 'pet_care.tiktok_dm.base_v1' / 'feminine.email.bd_v2'
    author          TEXT,                              -- 张 / 吴鑫然 / Mercy / etc
    channel         TEXT NOT NULL                      -- tiktok_dm / email / whatsapp / sms
                    CHECK (channel IN ('tiktok_dm','email','whatsapp','sms','other')),
    language        TEXT NOT NULL DEFAULT 'en',
    category_scope  TEXT NOT NULL DEFAULT 'all',
    subject         TEXT,
    body            TEXT NOT NULL,
    quality_rating  REAL,                              -- 0.0~5.0 人工评分
    is_active       INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
)
"""

CREATE_OUTBOX = """
CREATE TABLE IF NOT EXISTS outbox (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id           INTEGER REFERENCES creator(id) ON DELETE SET NULL,
    product_ids          TEXT,                          -- JSON array of product.id
    channel              TEXT NOT NULL DEFAULT 'tiktok_dm',
    language             TEXT NOT NULL DEFAULT 'en',
    subject              TEXT,
    body                 TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'draft'  -- draft / ready / copied / sent / failed / archived
                         CHECK (status IN ('draft','ready','copied','sent','failed','archived')),
    generated_by_feature TEXT,                          -- 'outreach_script' / 'manual'
    generation_meta_json TEXT,                          -- {"provider":"openai","model":"gpt-4o","compliance_flags":[]}
    template_used        TEXT,                          -- 'pet_care.tiktok_dm.base_v1'
    copied_at            TEXT,
    sent_at              TEXT,
    sent_by              TEXT,                          -- username of operator
    notes                TEXT,
    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now'))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_creator ON outbox(creator_id)",
    "CREATE INDEX IF NOT EXISTS idx_example_channel ON outreach_example(channel, category_scope, language)",
    "CREATE INDEX IF NOT EXISTS idx_brand_profile_scope ON brand_profile(category_scope, is_active)",
]


# ============================================================
# Resource registration in _meta_resource
# ============================================================
RESOURCE_ROWS = [
    # (name, table, pk, upsert_keys, json_cols, fk_lookup, description)
    ("app_config", "app_config", "key", ["key"], [], {},
     "系统级 KV 配置（outreach 政策 / 品牌资料 / 禁词 等）"),
    ("brand_profile", "brand_profile", "id", ["title"], [], {},
     "品牌资料条目"),
    ("outreach_example", "outreach_example", "id", ["template_key"], [], {},
     "历史话术 few-shot 样本库"),
    ("outbox", "outbox", "id", ["id"], ["product_ids", "generation_meta_json"],
     {"creator_handle": ["creator", ["handle"], "creator_id"]},
     "邀约话术触达队列（半自动化）"),
]


# ============================================================
# Seeds — v1 默认值
# ============================================================
APP_CONFIG_SEEDS = [
    # (key, value, type, category, description)
    ("outreach.commission_rate_default", "0.20", "number", "outreach",
     "默认达人佣金率（20%）— 优先于 product.commission_rate_default"),
    ("outreach.sampling_packs_per_creator", "1", "number", "outreach",
     "每位达人寄样数量（默认 1 包）"),
    ("outreach.sampling_eligible_skus", '"all_active"', "json", "outreach",
     "可寄样 SKU 范围：all_active = 所有 status=active 的 SKU；或写 SKU 数组"),
    ("outreach.shipping_days", "7", "number", "outreach",
     "物流时效（天）"),
    ("outreach.default_language", '"en"', "json", "outreach",
     "默认话术语言（en / zh / auto-by-country）"),
    ("outreach.default_channels", '["tiktok_dm"]', "json", "outreach",
     "默认启用的触达渠道（v1 仅 tiktok_dm）"),
    ("outreach.signature", "X9 Team", "string", "outreach",
     "默认 BD 签名"),
    ("outreach.brand_website", "x9x9.us", "string", "brand",
     "对外官网地址"),
    ("outreach.brand_email", "sales@sanitexindustries.com", "string", "brand",
     "对外回复邮箱"),
    ("outreach.banned_phrases", json.dumps([
        # 美区 TikTok 卫生巾品类合规红线
        "FDA-approved",                       # 必须改成 FDA registered
        "FDA approved",
        "the safest", "100% leak-proof", "best in the world", "world's best",
        "treat", "cure", "prevent disease", "prevents disease",
        "relieve period pain", "relieves period pain", "pain-free",
        "guaranteed sales", "guaranteed income", "no-risk high return",
        "100% effective", "completely safe",
    ], ensure_ascii=False), "json", "outreach",
     "禁词/禁说法清单（生成时强制拦截 + 替换建议）"),
    ("outreach.banned_replacements", json.dumps({
        "FDA-approved": "FDA registered",
        "FDA approved": "FDA registered",
        "100% leak-proof": "leak protection",
        "the safest": "thoughtfully designed",
        "treat": "support",
        "cure": "support",
    }, ensure_ascii=False), "json", "outreach",
     "禁词的推荐替换"),
]


BRAND_PROFILE_SEEDS = [
    # (title, body_text, source_path, category_scope, language, sort_order)
    ("X9 brand positioning",
     "X9 — Clean, Light & Free. A US care brand with Appalachian heritage, "
     "specializing in feminine, baby, adult, and pet care. We craft thoughtfully designed, "
     "skin-friendly, sensitive-skin-conscious hygiene essentials for everyday life.",
     "C达人建联/X9 brand（品牌介绍）.pptx", "all", "en", 1),

    ("X9 品牌定位（中文）",
     "X9 — Clean, Light & Free。美国本土护理品牌，源自 Appalachian 阿巴拉契亚地区，"
     "覆盖女性护理、母婴、成人护理、宠物护理四大品类，主打温和亲肤、敏感肌友好的日常护理产品。",
     "C达人建联/X9 brand（品牌介绍）.pptx", "all", "zh", 2),

    ("Pet care line summary",
     "Our pet care line includes pet diapers (male wraps, female diapers with tail-hole option), "
     "training pads, and underpads. Designed to keep homes clean during heat cycles, "
     "incontinence care, post-surgery recovery, and indoor potty training. "
     "Multiple sizes from XS to L; breathable, leak-protected, odor-locking.",
     "A社媒/宠物系列产品卖点梳理.docx", "pet", "en", 10),

    ("Feminine care line summary",
     "Our feminine care line covers cotton-cover panty liners, ultra-thin pads, "
     "cotton-cover pads (regular/super/overnight), and period underwear. "
     "100% pure cotton top sheet, fragrance-free, sensitive-skin friendly. "
     "FDA registered. Sizes for daily, medium-flow, and overnight needs.",
     "A社媒/女性系列产品卖点梳理.docx", "female_care", "en", 11),
]


OUTREACH_EXAMPLE_SEEDS = [
    # The user-provided FIXED pet-care DM script (with stated 20% commission, X9 Team signature)
    {
        "template_key": "pet_care.tiktok_dm.base_v1",
        "author": "X9 Team",
        "channel": "tiktok_dm",
        "language": "en",
        "category_scope": "pet",
        "subject": None,
        "body": (
            "Hello, I hope you're doing well.\n\n"
            "This is X9. We specialize in high-quality hygiene and care products, "
            "such as pet diapers and pet pads, designed to provide comfort, confidence, "
            "and daily protection for pets.\n\n"
            "We truly love your content and appreciate the genuine connection you've built "
            "with your audience. We'd like to warmly invite you to join us as a TikTok Core "
            "Creator Partner and introduce our products to your followers. You will earn a "
            "20% commission on all sales generated directly through your content.\n\n"
            "If you're open to collaboration, please let us know. Our main shop will then send "
            "you an invitation. If you have any questions, feel free to reach out anytime. "
            "We sincerely look forward to exploring potential collaboration with you!"
        ),
        "quality_rating": 4.5,
        "notes": "Fixed pet-care TikTok DM template — X9 Team signature, 20% commission, all SKUs eligible.",
    },
]


# ============================================================
# Run migration
# ============================================================
def main() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # 1. Tables
    for sql in [CREATE_APP_CONFIG, CREATE_BRAND_PROFILE, CREATE_OUTREACH_EXAMPLE, CREATE_OUTBOX]:
        con.execute(sql)
    for idx in CREATE_INDEXES:
        con.execute(idx)

    # 2. Register as resources in _meta_resource (so generic CRUD works)
    for name, table, pk, upsert, json_cols, fk, desc in RESOURCE_ROWS:
        con.execute(
            "INSERT INTO _meta_resource(name,table_name,pk,upsert_keys,json_cols,fk_lookup,"
            "description,is_dynamic,writable) VALUES(?,?,?,?,?,?,?,1,1) "
            "ON CONFLICT(name) DO UPDATE SET upsert_keys=excluded.upsert_keys, "
            "json_cols=excluded.json_cols, fk_lookup=excluded.fk_lookup, description=excluded.description",
            (name, table, pk, json.dumps(upsert), json.dumps(json_cols), json.dumps(fk), desc)
        )

    # 3. Seed app_config (only if missing — never overwrite admin's edits)
    n_cfg = 0
    for key, val, vtype, cat, desc in APP_CONFIG_SEEDS:
        cur = con.execute(
            "INSERT OR IGNORE INTO app_config(key,value,value_type,category,description) "
            "VALUES(?,?,?,?,?)", (key, val, vtype, cat, desc)
        )
        n_cfg += cur.rowcount

    # 4. Seed brand_profile (only if no row with same title)
    n_brand = 0
    for title, body, src, scope, lang, order in BRAND_PROFILE_SEEDS:
        if not con.execute("SELECT 1 FROM brand_profile WHERE title=?", (title,)).fetchone():
            con.execute(
                "INSERT INTO brand_profile(title,body_text,source_path,category_scope,language,sort_order) "
                "VALUES(?,?,?,?,?,?)", (title, body, src, scope, lang, order)
            )
            n_brand += 1

    # 5. Seed outreach_example
    n_ex = 0
    for ex in OUTREACH_EXAMPLE_SEEDS:
        if not con.execute(
            "SELECT 1 FROM outreach_example WHERE template_key=?", (ex["template_key"],)
        ).fetchone():
            con.execute(
                "INSERT INTO outreach_example(template_key,author,channel,language,"
                "category_scope,subject,body,quality_rating,notes) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (ex["template_key"], ex["author"], ex["channel"], ex["language"],
                 ex["category_scope"], ex.get("subject"), ex["body"],
                 ex.get("quality_rating"), ex.get("notes"))
            )
            n_ex += 1

    con.commit()

    # Summary
    print(f"[migrate_v7] tables ensured + 4 resources registered")
    print(f"[migrate_v7] app_config: +{n_cfg} new keys (existing untouched)")
    print(f"[migrate_v7] brand_profile: +{n_brand} new entries")
    print(f"[migrate_v7] outreach_example: +{n_ex} new templates")
    n_total = {
        "app_config": con.execute("SELECT COUNT(*) FROM app_config").fetchone()[0],
        "brand_profile": con.execute("SELECT COUNT(*) FROM brand_profile").fetchone()[0],
        "outreach_example": con.execute("SELECT COUNT(*) FROM outreach_example").fetchone()[0],
        "outbox": con.execute("SELECT COUNT(*) FROM outbox").fetchone()[0],
    }
    for k, v in n_total.items():
        print(f"   total {k}: {v}")
    con.close()


if __name__ == "__main__":
    main()
