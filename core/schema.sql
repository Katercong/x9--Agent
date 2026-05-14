-- ============================================================
-- X9 跨境数据库 - SQLite Schema
-- 单一可信源 (single source of truth) for products, creators, outreach
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------- 类目 ----------
CREATE TABLE IF NOT EXISTS category (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,           -- female_care/adult_care/pet/baby/home_care/mask
    name_zh     TEXT NOT NULL,
    name_en     TEXT,
    parent_id   INTEGER REFERENCES category(id),
    sort_order  INTEGER DEFAULT 0
);

-- ---------- 产品主表 ----------
CREATE TABLE IF NOT EXISTS product (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    sku_code                 TEXT UNIQUE NOT NULL,   -- BU02P155
    art_no                   TEXT,                   -- 货号 (通常等于 sku_code)
    name_en                  TEXT,
    name_zh                  TEXT,
    category_id              INTEGER REFERENCES category(id),
    subcategory              TEXT,                   -- 卫生巾/护垫/纸尿裤/隔尿垫/...
    series                   TEXT,                   -- 'Cotton Cover Pads'
    size_label               TEXT,                   -- 240mm / M / 56*56
    pcs_per_pack             INTEGER,
    packs_per_case           INTEGER,
    price_tiktok             REAL,
    price_temu               REAL,
    price_ebay               REAL,
    price_ebay_local         REAL,
    price_independent        REAL,
    currency                 TEXT DEFAULT 'USD',
    positioning_zh           TEXT,                   -- 低价高转化/中高客单/...
    tier                     TEXT,                   -- 1号主推/2号主推/3号主推/常规
    description_en           TEXT,
    description_zh           TEXT,
    selling_points_en        TEXT,                   -- JSON array
    selling_points_zh        TEXT,                   -- JSON array
    pain_points_zh           TEXT,                   -- JSON array
    scenarios_en             TEXT,                   -- JSON array
    scenarios_zh             TEXT,                   -- JSON array
    target_audience_en       TEXT,
    target_audience_zh       TEXT,
    proof                    TEXT,                   -- FDA registered / Dermatologically tested
    vocabulary_en            TEXT,                   -- JSON array (AI 文案词库)
    creative_angles_en       TEXT,                   -- JSON array
    safe_scenes_en           TEXT,                   -- JSON array (AI 生图安全镜头)
    focus_zh                 TEXT,                   -- 卖点重心提示
    amazon_url               TEXT,
    short_url                TEXT,
    tk_content_key           TEXT,                   -- 桥接 TK_Content workbench 的 PRODUCT_LIBRARY key
    commission_rate_default  REAL,
    creator_match_levels     TEXT,                   -- JSON array '["S","A","B"]'
    creator_persona_zh       TEXT,
    is_main_push             INTEGER DEFAULT 0,
    status                   TEXT DEFAULT 'active',  -- active/draft/inactive
    created_at               TEXT DEFAULT (datetime('now')),
    updated_at               TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_product_category    ON product(category_id);
CREATE INDEX IF NOT EXISTS idx_product_tk_key      ON product(tk_content_key);
CREATE INDEX IF NOT EXISTS idx_product_main_push   ON product(is_main_push);

-- ---------- 产品图片 ----------
CREATE TABLE IF NOT EXISTS product_image (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    rel_path      TEXT NOT NULL,                    -- 相对 Database/ 的相对路径
    kind          TEXT,                             -- main/package/content/scene/reference
    caption       TEXT,
    display_order INTEGER DEFAULT 0,
    UNIQUE(product_id, rel_path)
);

CREATE INDEX IF NOT EXISTS idx_product_image_pid ON product_image(product_id);

-- ---------- 达人主表 ----------
CREATE TABLE IF NOT EXISTS creator (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    handle              TEXT NOT NULL,             -- 不带 @
    platform            TEXT NOT NULL DEFAULT 'tiktok',  -- tiktok/instagram/youtube
    profile_url         TEXT,
    display_name        TEXT,
    country             TEXT,                       -- US/MX/GB/...
    language            TEXT,
    category_tags       TEXT,                       -- JSON array ['女性护理','母婴']
    followers           INTEGER,                    -- 53900
    followers_raw       TEXT,                       -- 原始字符串 53.9K
    tier                TEXT,                       -- S/A/B/C/D 自动按粉丝数划分
    avg_views           INTEGER,
    gmv_30d_usd         REAL,
    pps                 REAL,                       -- 内容表现分
    sample_score        REAL,
    post_rate_est       REAL,                       -- 0.0 ~ 1.0
    email               TEXT,
    whatsapp            TEXT,
    instagram_handle    TEXT,
    youtube_handle      TEXT,
    current_status      TEXT DEFAULT 'prospect',    -- prospect/contacted/confirmed/sample_shipped/sample_delivered/video_published/ad_authorized/ad_running/dropped
    store_assigned      TEXT,                       -- 店铺名 X9x9 Shop
    owner_bd            TEXT,                       -- 国内对接人 Mercy
    first_contact_date  TEXT,                       -- ISO date
    last_contact_date   TEXT,
    notes               TEXT,
    source              TEXT,                       -- tiktok_search/cm/referral/scraper/manual
    quality_score       REAL,                       -- 综合评分 (后续 AI 评分模型)
    created_at          TEXT DEFAULT (datetime('now')),
    updated_at          TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, handle)
);

CREATE INDEX IF NOT EXISTS idx_creator_tier   ON creator(tier);
CREATE INDEX IF NOT EXISTS idx_creator_status ON creator(current_status);
CREATE INDEX IF NOT EXISTS idx_creator_owner  ON creator(owner_bd);

-- ---------- 建联事件流水 ----------
CREATE TABLE IF NOT EXISTS outreach (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_id      INTEGER NOT NULL REFERENCES creator(id) ON DELETE CASCADE,
    event_date      TEXT,                          -- ISO date
    store_name      TEXT,
    bd_owner        TEXT,
    action          TEXT,                          -- contact/confirm/ship/deliver/post/authorize/run_ad/drop
    status          TEXT,                          -- 单条事件后达人新状态 (冗余便于审计)
    channel         TEXT,                          -- dm/email/whatsapp/cm
    message         TEXT,                          -- 邀约话术
    sample_qty      INTEGER DEFAULT 0,
    commission_rate REAL,
    video_url       TEXT,
    ad_auth_code    TEXT,
    remark          TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_outreach_creator ON outreach(creator_id);
CREATE INDEX IF NOT EXISTS idx_outreach_date    ON outreach(event_date);

-- ---------- 一次建联涉及的 SKU (多对多) ----------
CREATE TABLE IF NOT EXISTS outreach_sku (
    outreach_id INTEGER NOT NULL REFERENCES outreach(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES product(id),
    qty         INTEGER DEFAULT 1,
    PRIMARY KEY (outreach_id, product_id)
);

-- ---------- 达人 X 产品 兴趣/匹配 ----------
CREATE TABLE IF NOT EXISTS creator_product (
    creator_id INTEGER NOT NULL REFERENCES creator(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    relation   TEXT,                                 -- interest/sampled/posted/authorized
    note       TEXT,
    PRIMARY KEY (creator_id, product_id)
);

-- ---------- 团队人员 ----------
CREATE TABLE IF NOT EXISTS staff (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    role TEXT,                                       -- BD/PM/策划/剪辑/投放
    note TEXT
);

-- ---------- 审计日志 ----------
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    record_id   INTEGER,
    action      TEXT NOT NULL,                       -- insert/update/delete
    changes     TEXT,                                -- JSON
    operator    TEXT,
    ts          TEXT DEFAULT (datetime('now'))
);

-- ---------- 触发器: 自动维护 updated_at ----------
CREATE TRIGGER IF NOT EXISTS trg_product_updated
AFTER UPDATE ON product FOR EACH ROW
BEGIN
    UPDATE product SET updated_at = datetime('now') WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_creator_updated
AFTER UPDATE ON creator FOR EACH ROW
BEGIN
    UPDATE creator SET updated_at = datetime('now') WHERE id = NEW.id;
END;
