# X9 数据库 API 使用指南（廖）

负责 **TikTok/IG 爬虫 / 自动化邮件 / 视频跟踪 / 广告投放跟踪 / 后续新模块** 的同学看这份。

整套 API 是**统一的资源接口**（`/api/v1/*`），不管以后加多少新表（产品库、广告投放、订单、评论、内容库……）都是一套调用方式，**不需要后端再加端点**。

---

## 一、连接信息

| 项 | 值 |
|---|---|
| **基础 URL（局域网）** | `http://192.168.1.168:18765` |
| **你的 API Key** | 由张在前台"设置 → 用户管理 → 廖 → 签发新 Key"生成，**只显示一次**，张会复制粘贴给你 |
| **请求头**（写接口必填） | `X-API-Key: <你的 token>` |
| **Content-Type** | `application/json` |
| **OpenAPI 文档**（自动生成，可视化调试） | `http://192.168.1.168:18765/docs` |

> 🔐 **新版 RBAC 模型**：每人一把私人 Key，服务端 SHA-256 哈希存储，每次请求都重新校验。
> 你拿到的 Key 是 `admin` 角色（与张同级），可以写数据 / 建表 / 改 LLM 配置。
> 想确认自己身份：`GET /api/v1/auth/whoami`，返回 `{user_id, username, display_name, role, key_prefix}`。

> ⚠️ **如果 Key 丢了**：找张重发一把，旧 Key 撤销即可（撤销后立即失效）。

> 张那台电脑必须开机 + 同一公司 WiFi。连不上先在浏览器试 `http://192.168.1.168:18765/`，看到管理界面说明网络通；不通先 ping。

---

## 二、API 总览

```
GET  /api/v1/                        服务发现 (列出所有 resources、queries、行数)

# 资源元信息（哪些表能读写、字段是什么）
GET  /api/v1/resources               所有资源列表
GET  /api/v1/resources/{name}        单个资源的字段定义

# 通用 CRUD（对任意 resource 一样调用）
GET    /api/v1/data/{resource}                列表 (?limit=&offset=&q=&col=val&order_by=)
GET    /api/v1/data/{resource}/{id}           单条
POST   /api/v1/data/{resource}/bulk           批量 upsert (auth)
PATCH  /api/v1/data/{resource}/{id}           部分字段更新 (auth)
DELETE /api/v1/data/{resource}/{id}           删除 (auth)

# 自助建表（新模块自己加表，不用找张/Claude）
POST   /api/v1/tables                         创建新表+自动注册 (auth)
POST   /api/v1/tables/{name}/columns          给已有表加列 (auth)

# 命名查询（预定义的 SQL 配方，复用张的业务规则）
GET  /api/v1/queries                 列出所有命名查询
GET  /api/v1/queries/{name}          运行一个 (?param=value)
```

## 三、当前已有的 7 个内置 resource

| name | 表 | upsert key | 用途 |
|---|---|---|---|
| `creators` | `creator` | `[platform, handle]` | 达人主表 |
| `products` | `product` | `[sku_code]` | X9 产品主表 |
| `outreach` | `outreach` | `[id]` | 建联事件流水 |
| `product_images` | `product_image` | `[id]` | 产品图片 |
| `categories` | `category` | `[code]` | 类目 |
| `staff` | `staff` | `[name]` | 团队人员 |
| `audit_log` | `audit_log` | `[id]` | 审计日志（只读） |

调 `GET /api/v1/resources/{name}` 可以查到一张表的全部字段、类型、JSON 列、外键 lookup 配置。

## 四、命名查询（业务规则封装）

| name | 含义 | 参数 |
|---|---|---|
| `creators_to_contact` | 待发邀约的达人 | `category` `min_followers` `limit` |
| `creators_follow_up` | N 天没动静的达人 | `stale_days` `limit` |
| `creators_by_tier` | 按等级筛达人 | `tier` `limit` |
| `outreach_video_tracking` | 待刷视频曝光数据 | `stale_hours` `limit` |
| `outreach_auth_pending` | 视频已发但缺授权码 | `limit` |
| `products_main_push` | 主推 SKU | `limit` |

新业务规则需要新 query → 跟张说一声，让 Claude 加。

---

## 五、典型工作流（爬虫 / 邮件 / 视频跟踪）

### 场景 A：爬虫抓到一批 TikTok 达人入库

```bash
KEY="Ig1okkeriHKl_J8HIs4r06dDGAgsY1hPxTSiWlfOA1k"
BASE="http://192.168.1.168:18765"

curl -X POST "$BASE/api/v1/data/creators/bulk" \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  --data-binary '{
    "items": [
      {"handle":"newuser1","platform":"tiktok","followers":85000,"avg_views":4500,"category_tags":["女性护理"],"country":"US","source":"scraper_v1"},
      {"handle":"newuser2","platform":"tiktok","followers":420000,"avg_views":15000,"gmv_30d_usd":380000,"pps":4.7,"source":"scraper_v1"}
    ]
  }'
# 自动行为:
# 1. 按 (platform, handle) 去重 → 已存在变 update
# 2. tier 自动按 followers 算 (>=1M=S / 30W-100W=A / 10W-30W=B / 1W-10W=C / <1W=D)
# 3. profile_url 自动按 platform+handle 拼
```

返回：`{"resource":"creators","inserted":2,"updated":0,"skipped":0,"errors":[]}`

### 场景 B：拉待联系队列 → 发私信 → 写事件

```python
import requests
BASE = "http://192.168.1.168:18765"
KEY  = "Ig1okkeriHKl_J8HIs4r06dDGAgsY1hPxTSiWlfOA1k"
HDR  = {"X-API-Key": KEY}

# 1. 拉今天该联系的人
queue = requests.get(f"{BASE}/api/v1/queries/creators_to_contact",
                     params={"category": "女性护理", "min_followers": 10000, "limit": 50}).json()

for c in queue["items"]:
    # 2. 你的邮件/私信发送脚本...
    sent_ok = send_dm(c["profile_url"], message="...")

    # 3. 写事件 — outreach 用 creator_handle 自动找 creator_id (FK lookup)
    requests.post(f"{BASE}/api/v1/data/outreach/bulk",
                  json={"items": [{
                      "creator_handle": c["handle"],
                      "action": "contact",
                      "status": "contacted",
                      "channel": "dm",
                      "event_date": "2026-05-07",
                      "message": "实际发送的话术...",
                      "bd_owner": "auto_pipeline"
                  }]},
                  headers=HDR)
    # 上面这一步会自动:
    #  - 把 creator_handle -> creator_id (查 creator 表)
    #  - 把 creator.current_status 同步更新成 'contacted'
    #  - 把 creator.last_contact_date 更新成 2026-05-07
```

### 场景 C：定时刷新视频曝光数据

```python
# 1. 拉待刷新的视频列表 (24 小时未更新)
todo = requests.get(f"{BASE}/api/v1/queries/outreach_video_tracking",
                    params={"stale_hours": 24, "limit": 100}).json()

for row in todo["items"]:
    # 2. 你的爬视频统计脚本...
    stats = scrape_tk(row["video_url"])

    # 3. PATCH 单条 outreach 的指标列
    requests.patch(f"{BASE}/api/v1/data/outreach/{row['outreach_id']}",
                   json={
                       "video_views":    stats.views,
                       "video_likes":    stats.likes,
                       "video_comments": stats.comments,
                       "video_shares":   stats.shares,
                       "metrics_updated_at": datetime.utcnow().isoformat()
                   },
                   headers=HDR)
```

### 场景 D：定期刷新粉丝/GMV（达人指标 refresh）

```python
# PATCH 单个达人的指标
requests.patch(f"{BASE}/api/v1/data/creators/123",  # 123 是 creator.id
               json={"followers": 92000, "avg_views": 5100, "gmv_30d_usd": 18000},
               headers=HDR)
# tier 会自动按新 followers 重算
```

---

## 六、自助建新表（关键能力）

新模块需要一张全新的表（比如广告投放跟踪、视频时序数据、订单同步）—— **直接调 API 创建，不用动后端代码**。

### 示例：建 `ad_campaigns` 跟广告投放

```bash
curl -X POST "$BASE/api/v1/tables" \
  -H "Content-Type: application/json" -H "X-API-Key: $KEY" \
  --data-binary '{
    "name": "ad_campaigns",
    "description": "GMV 广告投放跟踪",
    "columns": [
      {"name": "campaign_id", "type": "TEXT",    "unique": true, "not_null": true},
      {"name": "creator_id",  "type": "INTEGER", "fk": "creator(id)"},
      {"name": "outreach_id", "type": "INTEGER", "fk": "outreach(id)"},
      {"name": "status",      "type": "TEXT",    "default": "running"},
      {"name": "budget_usd",  "type": "REAL"},
      {"name": "spend_usd",   "type": "REAL", "default": 0},
      {"name": "gmv_usd",     "type": "REAL", "default": 0},
      {"name": "roi",         "type": "REAL"}
    ],
    "upsert_keys": ["campaign_id"],
    "fk_lookup": {
      "creator_handle": ["creator", ["handle"], "creator_id"]
    }
  }'
```

返回：`{"ok": true, "name": "ad_campaigns", "table": "ad_campaigns", "create_sql": "..."}`

**建好后立即就能用 `/api/v1/data/ad_campaigns/*` 全套 CRUD**，无须重启服务、无须找后端：

```bash
# 写入数据 (FK lookup 把 creator_handle 自动转 creator_id)
curl -X POST "$BASE/api/v1/data/ad_campaigns/bulk" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data-binary '{"items":[
    {"campaign_id":"CAMP-001","creator_handle":"rizutravel","budget_usd":100,"spend_usd":42,"gmv_usd":210,"roi":5.0}
  ]}'

# 读出
curl "$BASE/api/v1/data/ad_campaigns?status=running&order_by=roi&desc=true"
```

### 给已有表加列

```bash
curl -X POST "$BASE/api/v1/tables/ad_campaigns/columns" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data-binary '{"name":"click_through_rate","type":"REAL","default":0}'
```

### 建表参数细节

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | resource 名（也是默认表名）。必须 `^[a-z_][a-z0-9_]*$`，不能以 `_` 开头（`_` 前缀保留给系统） |
| `table` | ❌ | 自定义底层表名，默认 = name |
| `columns[].name` | ✅ | 列名，同上正则 |
| `columns[].type` | ❌ | `TEXT` / `INTEGER` / `REAL` / `BLOB` / `NUMERIC`，默认 TEXT |
| `columns[].unique` | ❌ | true/false |
| `columns[].not_null` | ❌ | true/false |
| `columns[].default` | ❌ | 默认值。字符串自动加引号；写成 `"datetime('now')"` 这种带括号的会按 SQL 表达式处理 |
| `columns[].fk` | ❌ | 外键，如 `"creator(id)"` |
| `upsert_keys` | ❌ | 数组，bulk upsert 时按这些列去重 |
| `json_cols` | ❌ | 数组，这些列里的 list/dict 自动 JSON 编码 |
| `fk_lookup` | ❌ | dict, 写入时用业务 key 自动反查 id (见 outreach 例子) |

系统会自动:
- 在最前加 `id INTEGER PRIMARY KEY AUTOINCREMENT`
- 在最后加 `created_at TEXT DEFAULT (datetime('now'))`（除非你自己定义了 created_at）

---

## 七、查询参数速查（GET `/api/v1/data/{resource}`）

```
?limit=100&offset=0          分页（默认 100，最大 1000）
?q=keyword                   全 TEXT 列模糊搜索
?<col>=<val>                 任意列等值过滤（如 ?current_status=prospect&tier=B）
?order_by=<col>&desc=true    排序
```

例子：
```
GET /api/v1/data/creators?tier=A&current_status=prospect&order_by=followers&desc=true&limit=20
GET /api/v1/data/products?category_id=1&is_main_push=1
GET /api/v1/data/outreach?bd_owner=Mercy&order_by=event_date&desc=true&limit=50
```

---

## 八、错误码对照

| 状态 | 含义 | 处理 |
|---|---|---|
| 200 | 成功 | — |
| 400 | body / 参数 / 标识符 不合法 | 看 `detail` 字段 |
| 401 | API Key 缺失或错误 | 检查 `X-API-Key` 头 |
| 403 | resource 是只读（如 audit_log）/ built-in 资源不能改 schema | 不能强改 |
| 404 | resource 名错 / id 不存在 | 调 `GET /api/v1/resources` 列出所有 |
| 409 | 表/列已存在 | 不要重复建，或先 DROP |
| 500 | 服务器异常 | 找张排查（同时把 URL 和 response 给他） |

---

## 九、Python 客户端模板

```python
import requests
from datetime import datetime

class X9DB:
    def __init__(self, base="http://192.168.1.168:18765",
                 key="Ig1okkeriHKl_J8HIs4r06dDGAgsY1hPxTSiWlfOA1k"):
        self.base = base
        self.hdr = {"X-API-Key": key}

    # 通用 CRUD
    def list(self, resource, **filters):
        return requests.get(f"{self.base}/api/v1/data/{resource}", params=filters).json()
    def get(self, resource, row_id):
        return requests.get(f"{self.base}/api/v1/data/{resource}/{row_id}").json()
    def bulk(self, resource, items):
        return requests.post(f"{self.base}/api/v1/data/{resource}/bulk",
                             json={"items": items}, headers=self.hdr).json()
    def patch(self, resource, row_id, **fields):
        return requests.patch(f"{self.base}/api/v1/data/{resource}/{row_id}",
                              json=fields, headers=self.hdr).json()

    # 命名查询
    def query(self, name, **params):
        return requests.get(f"{self.base}/api/v1/queries/{name}", params=params).json()

    # 建表
    def create_table(self, name, columns, **kwargs):
        return requests.post(f"{self.base}/api/v1/tables",
                             json={"name": name, "columns": columns, **kwargs},
                             headers=self.hdr).json()

# ----- 用法 -----
db = X9DB()

# 拉队列
todo = db.query("creators_to_contact", category="女性护理", limit=20)
for c in todo["items"]:
    print(c["handle"], c["tier"], c["followers"])

# 入库爬虫结果
db.bulk("creators", [
    {"handle": "user1", "platform": "tiktok", "followers": 50000, "category_tags": ["母婴"]}
])

# 写建联事件
db.bulk("outreach", [
    {"creator_handle": "user1", "action": "contact", "status": "contacted",
     "channel": "dm", "event_date": "2026-05-07", "message": "邀约话术..."}
])

# 刷视频指标
db.patch("outreach", 42, video_views=12500, video_likes=980,
         metrics_updated_at=datetime.utcnow().isoformat())

# 加新表 (一次性)
db.create_table("ad_campaigns",
    columns=[
        {"name": "campaign_id", "type": "TEXT", "unique": True, "not_null": True},
        {"name": "creator_id",  "type": "INTEGER", "fk": "creator(id)"},
        {"name": "spend_usd",   "type": "REAL", "default": 0},
        {"name": "gmv_usd",     "type": "REAL", "default": 0},
    ],
    upsert_keys=["campaign_id"],
    fk_lookup={"creator_handle": ["creator", ["handle"], "creator_id"]},
    description="GMV 广告投放跟踪")
```

---

## 十、约定与最佳实践

1. **写之前先确认 resource 存在**：调 `GET /api/v1/resources/{name}` 看字段，避免 typo
2. **批量优于单条**：`/bulk` 端点一次几百条，比循环单写快得多
3. **不要直接 SQL**：所有写入走 API，方便审计 + 回滚 + 张这边 UI 看到
4. **新表自助建**：不要让张帮你加端点（张已经不需要写代码了）；建好的表自动有完整 CRUD
5. **错误信息看 `detail`**：FastAPI 错误体格式是 `{"detail":"..."}`，里面通常说清楚原因
6. **OpenAPI 文档**：`/docs` 是浏览器交互式调试页，可以直接试每个接口

## 十一、故障排查 checklist

1. **连不上 192.168.1.168:18765** → 张电脑没开服务，或不在同一 WiFi
2. **401 Unauthorized** → `X-API-Key` 头没带或写错
3. **400 invalid identifier** → 表/列名格式不对，必须 `^[a-z_][a-z0-9_]*$`
4. **400 fk_errors in errors[]** → 外键关联失败（比如 creator_handle 找不到达人），需要先 ingest creator
5. **403 read-only** → audit_log 这种只读表不能写
6. **响应 timeout** → 张那边 SQLite 可能在 reimport，等 30 秒重试

## 十二、调用 LLM (统一入口)

服务端有一个 LLM 配置中心，张在前台 "设置" tab 选 Provider + 配 Key + 激活。
廖这边**永远不需要直接处理 API Key** —— 所有 AI 调用走代理：

```
POST /api/v1/llm/complete
```

body：
```json
{
  "messages": [{"role":"user","content":"你的 prompt"}],
  "system": "可选：system prompt",
  "max_tokens": 1500,
  "temperature": 0.7,
  "provider": "anthropic",   // 可选；不传走当前 Active
  "model": "claude-sonnet-4-6"  // 可选；不传走 Provider 默认
}
```

返回：
```json
{
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "content": "AI 回的文字",
  "input_tokens": 234,
  "output_tokens": 567
}
```

支持的 Provider 协议：
- **anthropic**：Anthropic Messages API (Claude)
- **openai_compat**：OpenAI Chat Completions 协议（OpenAI / DeepSeek / Moonshot / 智谱 / 通义 ...）

廖也能自己加 Provider：
```bash
curl -X POST "$BASE/api/v1/llm/providers" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  --data-binary '{"code":"moonshot","display_name":"Kimi","type":"openai_compat","base_url":"https://api.moonshot.cn/v1","default_model":"moonshot-v1-8k"}'
```

但**配 Key + 激活**的操作建议让张在前台做（避免 Key 在多个地方泄露）。

错误码：
- `400` 没有激活的 Provider / 该 Provider 没设 Key → 找张到设置页配
- `502` upstream 报错（key 错、网络挂、模型名错）→ 看 `detail` 字段里的原始报错

## 十三、字段权威定义

完整 schema：[`schema.sql`](../schema.sql) + [`schema.md`](schema.md)
所有 resource 字段在线查：`GET /api/v1/resources`
