# X9 Database Schema Dump

> Generated: 2026-05-08
> Total tables: 35
> Database: SQLite (WAL mode)

---

## Overview

| Category | Tables |
|----------|--------|
| Core Business | creator, product, outreach, outbox, outreach_sku, creator_product, product_image |
| Category & Config | category, app_config |
| Content & Outreach | tk_hot_keyword, outreach_example, brand_profile |
| Security | api_user, api_key, audit_log |
| Competitor | competitor_brand, creator_competitor_collab |
| Crawler Extension | creators, extension_sessions, extension_run_progress, extension_commands, raw_observations |
| AI/LLM | llm_provider, llm_feature |
| Scoring & Tags | creator_recommendations, creator_tags, tag_definitions, review_tasks |
| Logging | system_logs, scrape_run, keyword_snapshot |
| Meta | _meta_resource, _meta_query |

---

## Table Details

### creator — 达人主表

**Rows: 66**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| handle | TEXT | N | — | 达人唯一标识（不带@），**Upsert Key** |
| platform | TEXT | N | 'tiktok' | tiktok/instagram/youtube |
| profile_url | TEXT | Y | — | 主页链接 |
| display_name | TEXT | Y | — | 显示名称 |
| country | TEXT | Y | — | 国家代码 US/UK/DE/ES... |
| language | TEXT | Y | — | 语言代码（固定en） |
| category_tags | TEXT | Y | — | JSON数组内容标签 |
| followers | INTEGER | Y | — | 粉丝数 |
| followers_raw | TEXT | Y | — | 原始字符串 53.9K |
| tier | TEXT | Y | — | S/A/B/C/D 按粉丝自动划分 |
| avg_views | INTEGER | Y | — | 平均播放量 |
| gmv_30d_usd | REAL | Y | — | 30天GMV（美元） |
| pps | REAL | Y | — | 内容表现分 |
| sample_score | REAL | Y | — | 寄样评分 |
| post_rate_est | REAL | Y | — | 发帖频率估算 0.0~1.0 |
| email | TEXT | Y | — | 联系邮箱 |
| whatsapp | TEXT | Y | — | WhatsApp号码 |
| instagram_handle | TEXT | Y | — | Instagram账号 |
| youtube_handle | TEXT | Y | — | YouTube账号 |
| current_status | TEXT | Y | 'prospect' | prospect/contacted/confirmed/sample_shipped/sample_delivered/video_published/ad_authorized/ad_running/dropped |
| store_assigned | TEXT | Y | — | 店铺名 |
| owner_bd | TEXT | Y | — | 国内对接人 |
| first_contact_date | TEXT | Y | — | ISO date |
| last_contact_date | TEXT | Y | — | ISO date |
| notes | TEXT | Y | — | 备注 |
| source | TEXT | Y | — | 数据来源 tiktok_search/cm/referral/scraper/manual |
| quality_score | REAL | Y | — | 综合评分 |
| engagement_rate | REAL | Y | — | 互动率 0~1 |
| last_post_at | TEXT | Y | — | 最后发帖时间 |
| excluded | INTEGER | N | 0 | 是否排除 |
| excluded_reason | TEXT | Y | — | 排除原因 |
| created_at | TEXT | Y | datetime('now') | 创建时间 |
| updated_at | TEXT | Y | datetime('now') | 更新时间 |

**Indexes:**
- `idx_creator_followers` (followers)
- `idx_creator_engagement` (engagement_rate)
- `idx_creator_excluded` (excluded)
- `idx_creator_owner` (owner_bd)
- `idx_creator_status` (current_status)
- `idx_creator_tier` (tier)
- UNIQUE (platform, handle)

---

### product — 产品主表

**Rows: 44**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| sku_code | TEXT | N | — | 商品编码，**Upsert Key** |
| art_no | TEXT | Y | — | 货号 |
| name_en | TEXT | Y | — | 英文名称 |
| name_zh | TEXT | Y | — | 中文名称 |
| category_id | INTEGER | Y | — | FK → category.id |
| subcategory | TEXT | Y | — | 卫生巾/护垫/纸尿裤/隔尿垫 |
| series | TEXT | Y | — | 系列 Cotton Cover Pads |
| size_label | TEXT | Y | — | 规格 240mm/M/56*56 |
| pcs_per_pack | INTEGER | Y | — | 每包片数 |
| packs_per_case | INTEGER | Y | — | 每箱包数 |
| price_tiktok | REAL | Y | — | TikTok价格 |
| price_temu | REAL | Y | — | Temu价格 |
| price_ebay | REAL | Y | — | eBay价格 |
| price_ebay_local | REAL | Y | — | eBay本地价格 |
| price_independent | REAL | Y | — | 独立站价格 |
| currency | TEXT | Y | 'USD' | 货币 |
| positioning_zh | TEXT | Y | — | 定位 低价高转化/中高客单 |
| tier | TEXT | Y | — | 1号主推/2号主推/3号主推/常规 |
| description_en | TEXT | Y | — | 英文描述 |
| description_zh | TEXT | Y | — | 中文描述 |
| selling_points_en | TEXT | Y | — | JSON英文卖点 |
| selling_points_zh | TEXT | Y | — | JSON中文卖点 |
| pain_points_zh | TEXT | Y | — | JSON痛点 |
| scenarios_en | TEXT | Y | — | JSON英文场景 |
| scenarios_zh | TEXT | Y | — | JSON中文场景 |
| target_audience_en | TEXT | Y | — | 英文目标受众 |
| target_audience_zh | TEXT | Y | — | 中文目标受众 |
| proof | TEXT | Y | — | 认证 FDA/Dermatologically tested |
| vocabulary_en | TEXT | Y | — | JSON AI文案词库 |
| creative_angles_en | TEXT | Y | — | JSON创意角度 |
| safe_scenes_en | TEXT | Y | — | JSON AI生图安全镜头 |
| focus_zh | TEXT | Y | — | 卖点重心提示 |
| amazon_url | TEXT | Y | — | Amazon链接 |
| short_url | TEXT | Y | — | 短链接 |
| tk_content_key | TEXT | Y | — | TK内容工作台key |
| commission_rate_default | REAL | Y | — | 默认佣金率 |
| creator_match_levels | TEXT | Y | — | JSON匹配等级 ["S","A","B"] |
| creator_persona_zh | TEXT | Y | — | 达人画像提示 |
| is_main_push | INTEGER | Y | 0 | 是否主推 |
| status | TEXT | Y | 'active' | active/draft/inactive |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

**FK:** category_id → category(id)

**Indexes:**
- `idx_product_category` (category_id)
- `idx_product_tk_key` (tk_content_key)
- `idx_product_main_push` (is_main_push)
- UNIQUE (sku_code)

---

### outreach — 建联事件流水

**Rows: 101**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| creator_id | INTEGER | N | — | FK → creator.id |
| event_date | TEXT | Y | — | ISO date |
| store_name | TEXT | Y | — | 店铺名 |
| bd_owner | TEXT | Y | — | BD负责人 |
| action | TEXT | Y | — | contact/confirm/ship/deliver/post/authorize/run_ad/drop |
| status | TEXT | Y | — | 事件后达人新状态 |
| channel | TEXT | Y | — | dm/email/whatsapp/cm |
| message | TEXT | Y | — | 邀约话术 |
| sample_qty | INTEGER | Y | 0 | 寄样数量 |
| commission_rate | REAL | Y | — | 佣金率 |
| video_url | TEXT | Y | — | 视频链接 |
| ad_auth_code | TEXT | Y | — | 广告授权码 |
| remark | TEXT | Y | — | 备注 |
| video_views | INTEGER | Y | — | 播放量 |
| video_likes | INTEGER | Y | — | 点赞数 |
| video_comments | INTEGER | Y | — | 评论数 |
| video_shares | INTEGER | Y | — | 分享数 |
| metrics_updated_at | TEXT | Y | — | 指标更新时间 |
| created_at | TEXT | Y | datetime('now') | |

**FK:** creator_id → creator(id)

**Indexes:**
- `idx_outreach_date` (event_date)
- `idx_outreach_creator` (creator_id)

---

### outbox — 邀约话术队列

**Rows: 0**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| creator_id | INTEGER | Y | — | FK → creator.id |
| product_ids | TEXT | Y | — | JSON数组 |
| channel | TEXT | N | 'tiktok_dm' | tiktok_dm/email/whatsapp |
| language | TEXT | N | 'en' | 语言 |
| subject | TEXT | Y | — | 主题 |
| body | TEXT | N | — | 话术内容 |
| status | TEXT | N | 'draft' | draft/ready/copied/sent/failed/archived |
| generated_by_feature | TEXT | Y | — | AI功能标识 |
| generation_meta_json | TEXT | Y | — | 生成元数据 |
| template_used | TEXT | Y | — | 使用的模板 |
| copied_at | TEXT | Y | — | 复制时间 |
| sent_at | TEXT | Y | — | 发送时间 |
| sent_by | TEXT | Y | — | 发送人 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

**FK:** creator_id → creator(id)

**Indexes:**
- `idx_outbox_creator` (creator_id)
- `idx_outbox_status` (status)

---

### product_image — 产品图片

**Rows: 3143**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| product_id | INTEGER | N | — | FK → product.id |
| rel_path | TEXT | N | — | 相对路径 |
| kind | TEXT | Y | — | main/package/content/scene/reference |
| caption | TEXT | Y | — | 说明 |
| display_order | INTEGER | Y | 0 | 显示顺序 |

**FK:** product_id → product.id (ON DELETE CASCADE)

**Indexes:**
- `idx_product_image_pid` (product_id)
- UNIQUE (product_id, rel_path)

---

### outreach_sku — 邀约×SKU多对多

**Rows: 86**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| outreach_id | INTEGER | N | — | FK → outreach.id |
| product_id | INTEGER | N | — | FK → product.id |
| qty | INTEGER | Y | 1 | 数量 |

**FK:** 
- outreach_id → outreach(id) (ON DELETE CASCADE)
- product_id → product(id)

**PK:** (outreach_id, product_id)

---

### creator_product — 达人×产品匹配

**Rows: 0**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| creator_id | INTEGER | N | — | FK → creator.id |
| product_id | INTEGER | N | — | FK → product.id |
| relation | TEXT | Y | — | interest/sampled/posted/authorized |
| note | TEXT | Y | — | 备注 |

**FK:**
- creator_id → creator(id) (ON DELETE CASCADE)
- product_id → product(id) (ON DELETE CASCADE)

**PK:** (creator_id, product_id)

---

### category — 品类

**Rows: 6**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| code | TEXT | N | — | 品类代码，**Unique** |
| name_zh | TEXT | N | — | 中文名 |
| name_en | TEXT | Y | — | 英文名 |
| parent_id | INTEGER | Y | — | FK → category.id（树形） |
| sort_order | INTEGER | Y | 0 | 排序 |

**Values:** female_care, adult_care, pet, baby, home_care, mask

---

### tk_hot_keyword — TikTok热搜关键词

**Rows: 28**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| keyword | TEXT | N | — | 关键词 |
| source_platform | TEXT | N | 'tiktok' | tiktok/amazon/google |
| region | TEXT | N | 'US' | US/UK/DE/ES... |
| category_hint | TEXT | Y | — | female_care/pet/baby... |
| search_volume | INTEGER | Y | — | 搜索量 |
| growth_rate | REAL | Y | — | 增长率 |
| rank_position | INTEGER | Y | — | 排名 |
| raw_metrics | TEXT | Y | — | 原始指标JSON |
| sample_evidence | TEXT | Y | — | 示例证据 |
| first_seen_at | TEXT | N | datetime('now') | 首次发现 |
| last_seen_at | TEXT | N | datetime('now') | 最后发现 |
| is_active | INTEGER | N | 1 | 是否活跃 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

**Indexes:**
- UNIQUE (keyword, source_platform, region)
- `idx_kw_recent` (last_seen_at)
- `idx_kw_category` (category_hint, is_active)
- `idx_kw_platform_region` (source_platform, region)

---

### outreach_example — 邀约话术模板

**Rows: 29**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| template_key | TEXT | Y | — | 模板标识 |
| author | TEXT | Y | — | 作者 |
| channel | TEXT | N | — | dm/email/whatsapp |
| language | TEXT | N | 'en' | 语言 |
| category_scope | TEXT | N | 'all' | 品类范围 |
| subject | TEXT | Y | — | 主题 |
| body | TEXT | N | — | 话术正文 |
| quality_rating | REAL | Y | — | 质量评分 |
| is_active | INTEGER | N | 1 | 是否启用 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |

---

### brand_profile — 品牌资料

**Rows: 4**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| title | TEXT | N | — | 标题 |
| body_text | TEXT | Y | — | 正文 |
| source_path | TEXT | Y | — | 来源路径 |
| category_scope | TEXT | N | 'all' | 品类范围 |
| language | TEXT | N | 'en' | 语言 |
| is_active | INTEGER | N | 1 | 是否启用 |
| sort_order | INTEGER | Y | 0 | 排序 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

---

### competitor_brand — 竞品品牌

**Rows: 25**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| code | TEXT | N | — | 品牌代码，**Unique** |
| display_name | TEXT | N | — | 显示名称 |
| category_scope | TEXT | N | 'all' | 品类范围 |
| home_country | TEXT | Y | — | 所属国家 |
| notes | TEXT | Y | — | 备注 |
| is_active | INTEGER | N | 1 | 是否启用 |
| created_at | TEXT | Y | datetime('now') | |

---

### creator_competitor_collab — 竞品合作记录

**Rows: 0**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| creator_id | INTEGER | N | — | FK → creator.id |
| competitor_brand_id | INTEGER | N | — | FK → competitor_brand.id |
| evidence_url | TEXT | Y | — | 证据链接 |
| detected_at | TEXT | Y | — | 发现时间 |
| confidence | REAL | Y | 1.0 | 置信度 0~1 |
| detection_source | TEXT | Y | — | 发现来源 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |

**FK:**
- creator_id → creator(id)
- competitor_brand_id → competitor_brand(id)

**Indexes:**
- `idx_collab_creator` (creator_id)
- `idx_collab_brand` (competitor_brand_id)

---

### api_user — API用户

**Rows: 2**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| username | TEXT | N | — | 用户名，**Unique** |
| display_name | TEXT | Y | — | 显示名 |
| role | TEXT | N | 'user' | admin/user/readonly |
| active | INTEGER | N | 1 | 是否激活 |
| notes | TEXT | Y | — | 备注 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

---

### api_key — API密钥

**Rows: 3**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| user_id | INTEGER | N | — | FK → api_user.id |
| key_hash | TEXT | N | — | SHA-256哈希，**Unique** |
| prefix | TEXT | N | — | Key前缀（用于识别） |
| description | TEXT | Y | — | 描述 |
| last_used_at | TEXT | Y | — | 最后使用时间 |
| expires_at | TEXT | Y | — | 过期时间 |
| revoked | INTEGER | N | 0 | 是否撤销 |
| created_at | TEXT | Y | datetime('now') | |

**FK:** user_id → api_user(id)

---

### audit_log — 审计日志

**Rows: 0**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| table_name | TEXT | N | — | 表名 |
| record_id | INTEGER | Y | — | 记录ID |
| action | TEXT | N | — | insert/update/delete |
| changes | TEXT | Y | — | JSON变更内容 |
| operator | TEXT | Y | — | 操作人 |
| ts | TEXT | Y | datetime('now') | 时间戳 |

---

### llm_provider — LLM提供商

**Rows: 3**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| code | TEXT | Y | — | 代码，**Unique** |
| display_name | TEXT | N | — | 显示名 |
| type | TEXT | N | — | 类型 |
| api_key | TEXT | Y | — | API密钥 |
| base_url | TEXT | Y | — | API地址 |
| default_model | TEXT | Y | — | 默认模型 |
| extra_headers | TEXT | Y | — | 额外头JSON |
| is_active | INTEGER | N | 0 | 是否激活 |
| enabled | INTEGER | N | 1 | 是否启用 |
| sort_order | INTEGER | N | 0 | 排序 |
| last_tested_at | TEXT | Y | — | 最后测试时间 |
| last_test_status | TEXT | Y | — | 测试状态 |
| last_test_message | TEXT | Y | — | 测试消息 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

---

### llm_feature — LLM功能

**Rows: 3**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| code | TEXT | Y | — | 功能代码，**Unique** |
| display_name | TEXT | N | — | 显示名 |
| description | TEXT | Y | — | 描述 |
| provider_code | TEXT | Y | — | FK → llm_provider.code |
| model | TEXT | Y | — | 模型 |
| temperature | REAL | Y | — | 温度 |
| max_tokens | INTEGER | Y | — | 最大token |
| sort_order | INTEGER | Y | 0 | 排序 |
| enabled | INTEGER | Y | 1 | 是否启用 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

**FK:** provider_code → llm_provider(code)

---

### app_config — 应用配置

**Rows: 11**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| key | TEXT | Y | — | 配置键，**Unique** |
| value | TEXT | Y | — | 配置值 |
| value_type | TEXT | N | 'string' | string/integer/float/boolean/json |
| category | TEXT | Y | — | 分类 |
| description | TEXT | Y | — | 描述 |
| updated_at | TEXT | Y | datetime('now') | |

---

### staff — 团队人员

**Rows: 8**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| name | TEXT | N | — | 姓名，**Unique** |
| role | TEXT | Y | — | BD/PM/策划/剪辑/投放 |
| note | TEXT | Y | — | 备注 |

---

### _meta_resource — 资源元数据

**Rows: 26**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| name | TEXT | Y | — | 资源名，**Unique** |
| table_name | TEXT | N | — | 表名 |
| pk | TEXT | Y | 'id' | 主键字段 |
| upsert_keys | TEXT | Y | — | Upsert键字段 |
| json_cols | TEXT | Y | — | JSON列 |
| fk_lookup | TEXT | Y | — | FK查找配置 |
| description | TEXT | Y | — | 描述 |
| is_dynamic | INTEGER | N | 1 | 是否动态表 |
| writable | INTEGER | N | 1 | 是否可写 |
| created_at | TEXT | Y | datetime('now') | |
| deprecated_note | TEXT | Y | — | 废弃说明 |

---

### _meta_query — 命名查询

**Rows: 13**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| name | TEXT | Y | — | 查询名，**Unique** |
| description | TEXT | Y | — | 描述 |
| sql | TEXT | N | — | SQL语句 |
| params | TEXT | Y | — | 参数定义JSON |
| is_builtin | INTEGER | N | 0 | 是否内置 |
| created_at | TEXT | Y | datetime('now') | |
| updated_at | TEXT | Y | datetime('now') | |

---

### keyword_snapshot — 关键词快照

**Rows: 39**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| keyword_id | INTEGER | N | — | FK → tk_hot_keyword.id |
| captured_at | TEXT | N | datetime('now') | 抓取时间 |
| search_volume | INTEGER | Y | — | 搜索量 |
| growth_rate | REAL | Y | — | 增长率 |
| rank_position | INTEGER | Y | — | 排名 |
| scrape_run_id | INTEGER | Y | — | FK → scrape_run.id |

**FK:**
- keyword_id → tk_hot_keyword(id)
- scrape_run_id → scrape_run(id)

---

### scrape_run — 爬虫运行记录

**Rows: 0**

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| id | INTEGER | Y | AUTO | Primary key |
| started_at | TEXT | N | datetime('now') | 开始时间 |
| finished_at | TEXT | Y | — | 结束时间 |
| source | TEXT | N | — | 来源 |
| region | TEXT | Y | 'US' | 地区 |
| triggered_by | TEXT | Y | — | 触发者 |
| operator | TEXT | Y | — | 操作人 |
| n_added | INTEGER | Y | 0 | 新增数 |
| n_updated | INTEGER | Y | 0 | 更新数 |
| n_errors | INTEGER | Y | 0 | 错误数 |
| status | TEXT | Y | 'running' | running/completed/failed |
| error_message | TEXT | Y | — | 错误消息 |
| notes | TEXT | Y | — | 备注 |

---

### creators — 爬虫达人队列（大表）

**Rows: 0**

47列详细结构略，主要字段：
- platform/handle/display_name/followers_count/email
- fit_level/priority_score/queue_type
- 各品类fit分: feminine_care_fit/pet_care_fit/home_care_fit/adult_care_fit/mom_baby_fit/health_mask_fit
- recommendation_status/outreach_priority/recommendation_score
- review_required/review_status

---

### creator_recommendations — AI推荐

**Rows: 0**

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(120) | PK |
| creator_id | VARCHAR(120) | FK |
| recommendation_status | VARCHAR(60) | |
| recommended_product_type | VARCHAR(60) | |
| recommended_collab_type | VARCHAR(60) | |
| outreach_priority | VARCHAR(8) | |
| recommendation_score | INTEGER | |
| recommendation_reason | TEXT | |
| risk_summary | TEXT | |
| next_action | TEXT | |

---

### creator_tags — 达人标签

**Rows: 0**

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(120) | PK |
| creator_id | VARCHAR(120) | FK |
| tag_code | VARCHAR(120) | |
| tag_type | VARCHAR(40) | |
| source | VARCHAR(80) | |
| confidence | FLOAT | |
| evidence_text | TEXT | |

---

### tag_definitions — 标签定义

**Rows: 79**

| Column | Type | Description |
|--------|------|-------------|
| tag_code | VARCHAR(120) | PK |
| tag_name | VARCHAR(200) | |
| tag_type | VARCHAR(40) | |
| description | TEXT | |
| is_active | INTEGER | |

---

### review_tasks — 复审任务

**Rows: 0**

| Column | Type | Description |
|--------|------|-------------|
| id | VARCHAR(120) | PK |
| creator_id | VARCHAR(120) | FK |
| task_type | VARCHAR(60) | |
| status | VARCHAR(20) | pending/completed |
| risk_tags_json | TEXT | |
| reason | TEXT | |
| reviewer_notes | TEXT | |

---

### Extension表（爬虫用）

- `extension_sessions` (0行) — 浏览器扩展会话
- `extension_run_progress` (0行) — 爬虫进度
- `extension_commands` (0行) — 扩展指令队列
- `raw_observations` (0行) — 原始观察数据
- `system_logs` (0行) — 系统日志

---

## Upsert Key汇总

| Table | Upsert Key |
|-------|------------|
| creator | (platform, handle) |
| product | sku_code |
| tk_hot_keyword | (keyword, source_platform, region) |
| creator_competitor_collab | (creator_id, competitor_brand_id) |
| product_image | (product_id, rel_path) |
| outreach_sku | (outreach_id, product_id) |
| creator_product | (creator_id, product_id) |
| category | code |
| competitor_brand | code |
| api_user | username |
| api_key | key_hash |
| llm_provider | code |
| llm_feature | code |
| app_config | key |
| staff | name |

---

## 数据行数统计

| 有数据 | 行数 |
|--------|------|
| product_image | 3143 |
| outreach | 101 |
| outreach_sku | 86 |
| creator | 66 |
| tag_definitions | 79 |
| competitor_brand | 25 |
| outreach_example | 29 |
| tk_hot_keyword | 28 |
| keyword_snapshot | 39 |
| product | 44 |
| category | 6 |
| staff | 8 |
| brand_profile | 4 |
| llm_provider | 3 |
| api_key | 3 |
| llm_feature | 3 |
| app_config | 11 |
| api_user | 2 |

| 空表 | 行数 |
|------|------|
| audit_log | 0 |
| outbox | 0 |
| creator_product | 0 |
| creator_competitor_collab | 0 |
| creators | 0 |
| creator_recommendations | 0 |
| creator_tags | 0 |
| review_tasks | 0 |
| scrape_run | 0 |
| extension_sessions | 0 |
| extension_run_progress | 0 |
| extension_commands | 0 |
| raw_observations | 0 |
| system_logs | 0 |

---

*End of Schema Dump*
