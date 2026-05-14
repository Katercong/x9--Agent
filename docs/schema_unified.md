# 统一后的数据库 Schema

> 这份是 2026-05-11 migrate_v16 之后的 PostgreSQL x9db 表清单。
> 完整 schema 用 `docker exec x9-postgres pg_dump -U x9 -s -d x9db` 获取最新。

## 达人相关(本次合并的重点)

### `creators` — 达人主表(统一后)

**主键:** `id TEXT`(UUID 字符串)
**唯一约束:** `(platform, handle)`

包含来自 A(原 F:\Database creator 表)和 B(原 desktop creators 表)的所有字段。166 行(132 从 A 合并 + 34 纯 B)。

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `id` | TEXT | B | UUID 主键 |
| `legacy_int_id` | INTEGER | 本次新加 | A 旧主键(int),便于反查 |
| `platform` | TEXT | 两边 | "tiktok" / "youtube" 等 |
| `handle` | TEXT | 两边 | 用户名(不含 @) |
| `display_name` | TEXT | 两边 | |
| `email` | TEXT | 两边 | |
| `has_email` | BOOLEAN | B | |
| `followers_count` | BIGINT | B (mapped from A `followers`) | |
| `followers_raw` | TEXT | 两边 | "1.2M" 这种 |
| `country` / `language` | TEXT | 本次新加(A only) | |
| `category_tags` | JSONB | 本次新加(A only) | |
| `gmv_30d_usd`, `pps`, `quality_score`, `sample_score` | NUMERIC | 本次新加(A only) | |
| `whatsapp`, `instagram_handle`, `youtube_handle` | TEXT | 本次新加(A only) | |
| `first_contact_date`, `last_contact_date` | TIMESTAMP | 本次新加(A only) | |
| `priority_score`, `fit_level`, `outreach_priority` | 多种 | B(评分流水线) | |
| `current_status` | TEXT | 两边 | "prospect" / "contacted" / ... |
| `store_assigned`, `owner_bd` | TEXT | 两边 | 业务运营字段 |
| `source` | TEXT | 本次新加(A only) | 来源标记 |
| (...其余 50+ B 来源的评分/打标/推荐字段) | | | 详见 `desktop/backend/models/creator.py` |

### `creator` — A 旧主表(legacy)

**保留不删**,FK 关系完整(`creator_product`, `outreach`, ... 仍引用)。
本次没有 rename,因为同时改 20+ 处 SQL 引用风险大,放到下一阶段做。

写入入口建议都指向 `creators`,`creator` 表只读。

### `tk_creators` — 廖的 lead pool 镜像

写入:廖的爬虫 / `core/scripts/migrate_sqlite_to_postgres.py` 把 B 的 creators 字段也镜像到这里。
读取:廖的爬虫专用。

## 产品 / 建联(来自 A,完整迁到 postgres)

| 表 | 行数 | 说明 |
|----|------|------|
| `product` | 44 | SKU 主数据 |
| `product_image` | 3143 | 商品图,关联到 product |
| `category` | 6 | 商品分类 |
| `outreach` | 101 | 建联事件 |
| `outreach_sku` | 86 | 建联事件 ↔ 商品 多对多 |
| `creator_product` | 0 | 达人 ↔ 商品 多对多 |
| `staff` | 8 | 团队成员 |
| `audit_log` | 0 | 审计日志(本地 dev 无内容) |
| `webhook_subscriber` | 0 | v15 加的 webhook 订阅者 |

## B 来源的子系统

| 表 | 行数 | 说明 |
|----|------|------|
| `raw_observations` | 1914 | 扩展抓到的原始观察(append-only) |
| `creator_tags` | ? | 达人 ↔ tag 多对多 |
| `tag_definitions` | (seeded) | tag 字典 |
| `creator_recommendations` | ? | 推荐历史(append-only) |
| `extension_sessions` | 5 | 扩展心跳/会话 |
| `extension_commands` / `extension_run_progress` | ? | 扩展任务调度 |
| `outreach_emails` | ? | 邮件草稿/已发 |
| `outreach_templates` | ? | 邮件模板 |
| `gmail_accounts` | ? | Gmail OAuth 凭据 |
| `review_tasks` | ? | 人工审核队列 |

## Core 系统表

| 表 | 说明 |
|----|------|
| `app_config` | 应用配置(Core 端) |
| `_meta_query` | 命名查询(v1.py 用) |
| `_meta_resource` | 资源注册(v1.py generic CRUD 用) |
| `llm_provider` | LLM 厂商配置 |
| `llm_feature` | 每个 AI 功能绑定哪个 provider |
| `api_user` / `api_key` | Core 自己的认证 |
| `migration_manifest` | 历次迁移的 JSON 摘要 |
| `app_session` / `app_user` / `system_log` | Desktop 自己的认证/日志 |

## 关键索引

`migrate_v16` 之后保证存在:

```
idx_creators_legacy_int_id        创新 (本次)
uq_creators_platform_handle       创新 (本次)
idx_creators_handle_pg            B 原有
uq_tk_creators_platform_handle_pg B 原有
idx_raw_observations_hash_pg      B 原有
```

## 命名差异表(A 风格 ↔ B 风格)

代码迁移时常用映射,详见 `core/app/creator_compat.py`:

| A | B |
|---|---|
| `id`(INTEGER) | `legacy_int_id`(INTEGER)+ `id`(UUID TEXT) |
| `followers` | `followers_count` |
| (无) | `department_code` |
| (无) | `search_keyword`, `source_video_*` |
| `category_tags` (JSON TEXT) | `category_tags` (JSONB) + 分散的评分字段 |

## 待办

- [ ] 把 `core/app/v1.py` 从 SQLite 移植到 PostgreSQL(目前 `creator/database.db` 还在被它读写)
- [ ] 完成后 rename `creator` → `creator_legacy`,删 `creator/database.db`
- [ ] 写一个 view `creator` 来兼容旧代码,直到所有读路径都改完
