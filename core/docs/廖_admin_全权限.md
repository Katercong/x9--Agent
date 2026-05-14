# 廖 · admin 全权限速查（v3.8.0）

> 张拍板：缺什么自己改。这页是你独立操作 X9 数据库的全部入口。
> 详细字段参考 → [廖_API使用指南.md](廖_API使用指南.md) ｜ schema 全列表 → [schema_dump.md](schema_dump.md)

---

## v3.8.2（2026-05-08 晚）— DROP 端点 + key scope 分级

按你需求单 P3 #9 + #10：

### DROP 端点
```bash
DELETE /api/v1/tables/<name>?confirm=true               # 删 dynamic 表（built-in 拒）
DELETE /api/v1/tables/<name>/columns/<col>?confirm=true # 删某列（built-in/dynamic 都行）
```
- 必须带 `?confirm=true`（防误操作）
- 拒绝删的列：PK / upsert_keys / json_cols / fk_lookup 涉及的列
- 删 built-in 表 → 仍要走 migrate_v*.py（API 不让，故意的）

### Key scope 分级
给 key 加 `scopes` 后，权限收敛到指定 resource pattern：

```bash
# 1. admin 签新 key（默认无 scope = 全权限）
POST /api/v1/auth/users/2/keys  →  { token, key_id }

# 2. 设 scope（admin 操作）
PATCH /api/v1/auth/keys/<key_id>/scopes
Body: {"scopes": ["write:tk_*", "read:*"]}

# 3. 清 scope（恢复 role 默认）
PATCH /api/v1/auth/keys/<key_id>/scopes
Body: {"scopes": null}
```

scope 字符串：
| 形式 | 含义 |
|---|---|
| `'admin'` | 全部资源全部操作（同 admin role）|
| `'admin:tk_*'` | 仅 tk_* 开头资源的 admin（含 DDL）|
| `'write:tk_*'` | 仅 tk_* 资源的写权限（bulk/patch/delete）|
| `'read:*'` | 全部资源读（GET 当前公开，预留）|

层级：admin > write > read（高级隐含低级）。pattern 用 fnmatch。

**典型用例**：你给爬虫 worker 签一把 key，scopes=`['write:tk_*']`。worker 灌 tk_creators 没问题，但碰张主表 `creator` 直接 403。worker 部署到外面也不会拿走全权限。

---

## v3.8.1（2026-05-08）— 高级查询语法已上线

按你需求单 P0+P1 全部实现，**5K+ 行规模 SQL 级**：

| 语法 | SQL 等价 | 用例 |
|---|---|---|
| `?col__gte=N` `__lte` `__gt` `__lt` | `col >= N` 等 | 粉丝/评分滑块 |
| `?col__in=a,b,c` 或重复 `?col=a&col=b` | `col IN (...)` | 多状态筛选 |
| `?col__icontains=text` | `col LIKE %text%` 不区分大小写 | UI 搜索框定位列 |
| `?col__like=%text%` | 透传 SQL LIKE | 含通配符的精确控制 |
| `?col__isnull=true\|false` | `IS NULL` / `IS NOT NULL` | 有/无邮箱筛选 |
| `?order_by=col1:desc,col2:asc` | 多键 ORDER BY | 4 键链排序一次完成 |

例：
```
/api/v1/data/tk_creators?followers_count__gte=10000&recommendation_score__lte=80&order_by=outreach_priority:asc,recommendation_score:desc&limit=50
```

P2/P3 还没动（JOIN/视图、WS 推送、scope 分级、DROP 端点）—— 见本文档末尾"P3 #8 误会澄清"。

---

## 一、连接

| 项 | 值 |
|---|---|
| **Base URL（LAN）** | `http://192.168.1.168:18765` |
| **你的 admin token** | 在张电脑 `F:\Claude_Project\Database\.local_keys_backup.txt`，"廖 (liao) — admin" 那行 |
| **请求头** | `X-API-Key: <token>` + `Content-Type: application/json` |
| **可视化调试**（OpenAPI） | `http://192.168.1.168:18765/docs` ← **打开就能点**，自动生成所有端点的表单 |
| **角色** | `admin`（和张同级，无任何写入限制） |

> 验证身份一行：
> ```bash
> curl -H "X-API-Key: <token>" http://192.168.1.168:18765/api/v1/auth/whoami
> ```

---

## 二、你作为 admin 能干的所有事（按破坏力升序）

### ① 读任何东西（永不报错）
```bash
GET /api/v1/                          # 服务发现，列出全部资源 + 命名查询
GET /api/v1/data/<resource>?limit=500&q=<关键词>&<col>=<值>
GET /api/v1/data/<resource>/<id>
GET /api/v1/queries/<name>?<参数>
GET /api/v1/resources                 # 所有资源元信息
```

### ② 写数据（按 upsert_keys 自动去重）
```bash
POST /api/v1/data/<resource>/bulk
Body: {"items": [{...}, {...}]}
返回: {"inserted": N, "updated": M, "skipped": K, "errors": [...]}
```
- `inserted` = 新增数；`updated` = 命中 upsert_keys 后更新数；不会重复插
- 单条更新：`PATCH /api/v1/data/<resource>/<id>` body 是部分字段
- 删除：`DELETE /api/v1/data/<resource>/<id>`（admin only）

### ③ **加列到任何表**（v3.8.0 新解锁，admin 可改内置表）
```bash
POST /api/v1/tables/<resource>/columns
Body: {"name": "你的字段名", "type": "TEXT|INTEGER|REAL|BLOB|NUMERIC", "default": 0}
```
**不再卡 `is_dynamic`**。可对 `creator`/`outreach`/`product` 等张的核心表加字段。
建议：加之前到群里说一声 + 自己同步更新 [docs/CHANGELOG.md](CHANGELOG.md)（新加字段标 `+`）。

### ④ 建新表（自动注册成 resource）
```bash
POST /api/v1/tables
Body: {
  "name": "ad_campaigns",                     # URL slug
  "table": "ad_campaigns",                    # SQL 表名（可省略，默认同 name）
  "columns": [
    {"name": "campaign_id", "type": "TEXT", "unique": true, "not_null": true},
    {"name": "spend_usd", "type": "REAL"},
    {"name": "creator_id", "type": "INTEGER", "fk": "creator(id)"}
  ],
  "upsert_keys": ["campaign_id"],
  "json_cols": [],
  "description": "TT 广告投放数据"
}
```
建完立刻能用 `/api/v1/data/ad_campaigns/bulk`。无需重启服务、无需改代码。

### ⑤ 改 LLM 配置（包括加 provider、绑功能）
```bash
POST /api/v1/data/llm_provider/bulk          # 加新 provider
PATCH /api/v1/data/llm_feature/<id>          # 改某 AI 功能用哪个模型
```

### ⑥ 加/改命名查询（业务 SQL 配方）
```bash
POST /api/v1/queries                          # 新增
PUT  /api/v1/queries/<name>                   # 覆盖（甚至能覆盖内置查询）
```
```json
{
  "name": "my_pet_creators_high_priority",
  "description": "我的高优先级宠物达人",
  "sql": "SELECT * FROM creators WHERE primary_product_category='pet_care' AND priority_score >= :min_score ORDER BY priority_score DESC LIMIT :limit",
  "params": [["min_score","int",70],["limit","int",50]]
}
```

### ⑦ 删数据 / 删表 / 删列 / 撤销 token
- `DELETE /api/v1/data/<resource>/<id>` — 删行
- `DELETE /api/v1/tables/<name>?confirm=true` — drop 整张 dynamic 表（built-in 拒，得走 migrate_v*）
- `DELETE /api/v1/tables/<name>/columns/<col>?confirm=true` — drop 一列（PK/upsert_keys/json_cols/fk 涉及列拒）
- `DELETE /api/v1/queries/<name>` — 删命名查询（内置查询不能删，可 PUT 覆盖）
- 用户管理：`/api/v1/auth/users`、`/api/v1/auth/keys`（包括 PATCH /scopes 给 key 设权限）

---

## 三、v3.8.0 你专属的 10 张表（lead 池 + 扩展协调）

| URL slug | 底层表 | upsert key | 你拿来干啥 |
|---|---|---|---|
| **`creator_leads`** | `creators`（VARCHAR id）| `[platform, handle]` | **爬虫主输出，灌这里** |
| `raw_observations` | `raw_observations` | `[content_hash]` | 抓取原始 JSON 留底，按 hash 去重 |
| `tag_definitions` | `tag_definitions` | `[tag_code]` | 79 个种子词已 seed，加新词直接 bulk |
| `creator_tags` | `creator_tags` | `[creator_id, tag_code]` | lead × tag 多对多 |
| `creator_recommendations` | 同名 | `[id]` | AI 推荐结果，按 rec_version 多版本 |
| `review_tasks` | 同名 | `[id]` | 人工审核队列 |
| `system_logs` | 同名 | `[id]` | 你端 append-only 日志 |
| `extension_sessions` | 同名 | `[worker_id]` | Chrome 扩展心跳，30s 一调 upsert |
| `extension_commands` | 同名 | `[id]` | 给扩展下命令的队列 |
| `extension_run_progress` | 同名 | `[worker_id]` | 每 worker 一条运行进度 |

> ⚠️ URL 是 `creator_leads`，**底层表是 `creators`**（复数）。张的主表是 `creator`（单数, INTEGER id），URL slug `creators` —— 不要混。

---

## 四、Cookbook（10 个最常见操作）

```bash
# 1. 看你登录的是谁
curl -H "X-API-Key: $T" http://192.168.1.168:18765/api/v1/auth/whoami

# 2. 看所有可用资源 + 行数
curl -H "X-API-Key: $T" http://192.168.1.168:18765/api/v1/

# 3. 灌爬虫数据（按 platform+handle 自动去重）
curl -X POST -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"items":[{"id":"abc","platform":"tiktok","handle":"x","followers_count":12345,"priority_score":80,"fit_level":"A","primary_product_category":"feminine_care"}]}' \
  http://192.168.1.168:18765/api/v1/data/creator_leads/bulk

# 4. 给 creator 主表加新字段（admin 现在能干）
curl -X POST -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"name":"tt_video_quality_score","type":"REAL","default":0}' \
  http://192.168.1.168:18765/api/v1/tables/creators/columns

# 5. 扩展心跳上报（worker 自己上报）
curl -X POST -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"items":[{"id":"sess_w1","extension_id":"chrome_x9","worker_id":"w1","status":"online","tiktok_login_status":"logged_in"}]}' \
  http://192.168.1.168:18765/api/v1/data/extension_sessions/bulk

# 6. 看现在哪些 worker 在线（自己写命名查询）
curl -X POST -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"name":"workers_online","description":"5 分钟内有心跳的 worker","sql":"SELECT worker_id, status, current_url, last_heartbeat_at FROM extension_sessions WHERE last_heartbeat_at >= datetime(\"now\",\"-5 minutes\")","params":[]}' \
  http://192.168.1.168:18765/api/v1/queries

# 7. 跑命名查询
curl -H "X-API-Key: $T" http://192.168.1.168:18765/api/v1/queries/workers_online

# 8. 取下一条 pending 命令（手动两步：查 → patch claimed_at）
curl -H "X-API-Key: $T" "http://192.168.1.168:18765/api/v1/data/extension_commands?status=pending&order_by=created_at&limit=1"
curl -X PATCH -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"status":"claimed","claimed_at":"2026-05-08T10:00:00"}' \
  http://192.168.1.168:18765/api/v1/data/extension_commands/<id>

# 9. ETL：把 lead 池里 fit=S 且 priority>=80 的拿出来准备进主表
curl -H "X-API-Key: $T" "http://192.168.1.168:18765/api/v1/data/creator_leads?fit_level=S&order_by=priority_score&desc=true"

# 10. 加 review_task（人工审核队列）
curl -X POST -H "X-API-Key: $T" -H "Content-Type: application/json" \
  -d '{"items":[{"id":"rev_001","creator_id":"abc","task_type":"verify_email","status":"pending","reason":"邮箱看着像垃圾箱"}]}' \
  http://192.168.1.168:18765/api/v1/data/review_tasks/bulk
```

---

## 五、做完了通知谁

| 改动 | 谁要知道 | 怎么通知 |
|---|---|---|
| 加新表 / 加新字段 | 张 | 微信群说一声 + 自己 PR `docs/CHANGELOG.md` 加 `+` 行 |
| 删字段 / 改字段类型 | 张 | **先公告 3 天 + 标 `deprecated_note`**，详见 [协作约定.md](协作约定.md) |
| 加命名查询 | 没人，自己用 | 可选 `docs/CHANGELOG.md` |
| 改 LLM provider/feature 绑定 | 张（影响他成本） | 群里说一声 |

---

## 六、玩坏了怎么办

| 场景 | 怎么救 |
|---|---|
| **API Key 丢了** | 让张跑 `reset_key.bat liao` 给你重发 |
| **改坏了某个表** | 张备份在 `database.db`，PR 前先 `cp database.db database.db.bak.<日期>` |
| **想撤销某个改动** | 加列没法 drop（SQLite 3.35 之前限制）；删的话需要重建表 → 让张评估 |
| **疑似看到错数据** | 先 `GET /api/v1/audit_log?limit=20` 看最近的写入流水 |
| **服务不响应** | 张那台电脑上 `restart.bat`，30 秒恢复 |

---

## 七、不要做的事（admin 也别碰）

- **不要直接 `DROP TABLE`**：API 没这个端点（故意的）。要删表走 `migrate_v*.py` + 张审过
- **不要改 `_meta_resource` / `_meta_query` / `api_user` / `api_key`**：这是治理层，乱改自己也登不上来
- **不要把 admin token 贴进任何代码仓库**：写在本地 env / 1Password / 张电脑 `.local_keys_backup.txt`
- **不要绕开 API 直接写 `database.db`**：审计日志 / 自动 trigger / JSON 编码全部失效

---

**你现在可以独立操作**。任何"我能不能 ..." 的问题，先看 `http://192.168.1.168:18765/docs` 的 OpenAPI —— 没在那的就是禁的，没禁的就是允许。

---

## 八、关于"P3 #8 schema 锁失效"—— 误会澄清

你在需求单里说："probe 测试发现 `POST /api/v1/tables/creators/columns` 居然返回 200，文档里写的 403 schema 锁没生效"。

**这不是 bug，是 v3.8.0 的明确决策（D-015）**：

| 历史 | 现状 |
|---|---|
| ≤v3.7：`is_dynamic=False` 资源（built-in: creator/outreach/product 等）即使 admin 也不能加列，必须改 `migrate_v*.py` 重启服务 | v3.8.0 起：admin 可改任何表 schema，is_dynamic 锁解除 |

**为什么解锁**：你需求单里抱怨过"加字段还要找张"。张拍板把 add_column 对 admin 开放，省去往返。

**仍然安全的部分**：
- `require_admin` 依赖**没动** —— readonly/user 角色调任何 DDL 端点照样 403
- 你的 probe 测试两把 key（A 和 B）行为一致，是因为**两把都是 admin key**，不是"任何 key 都能改"
- 验证：随便给一个 user 角色的 key 跑 add_column，会被 401/403 顶回来

**probe 留下的脏数据已清**：
```
✓ ALTER TABLE creator DROP COLUMN probe_x_a_1778226698
✓ ALTER TABLE creator DROP COLUMN probe_x_b_1778226698
✓ DROP TABLE liao_keytest_20260508_155138_a
✓ DROP TABLE liao_keytest_20260508_155138_b
```

如果你确实想要 P3 #9 的 **scope 分级**（read/write/admin 三档，限定到资源前缀），告诉张去 D-016 走流程。当前只有 role 三档 (admin/user/readonly)，未实现 scope。
