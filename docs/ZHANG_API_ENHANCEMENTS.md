# 给张：X9 API 后续增强需求单

**背景**：廖这边的 desktop app 已经全切到远端 X9 DB（`tk_creators` 表 130 行）。
当前用客户端过滤 + 排序兜底，130 行规模没问题；但 API 层缺几个查询能力，
等数据涨到 5K+ 行就会成为瓶颈。下面按优先级列出来，**不急，先把现有的稳定运行一段时间再做**。

---

## P0 — 强烈建议（直接影响 desktop app UI 性能）

### 1. 区间查询 `__gte` / `__lte`

**用例**：UI 里有"粉丝数 ≥ N"、"评分 ≥ M"、"评分 ≤ K"等滑块。当前只能 fetch 全表回客户端过滤。

**建议接口**：
```
GET /api/v1/data/tk_creators?followers_count__gte=10000&recommendation_score__lte=80
```

**实现思路**：在 resource 路由里把 `?<col>__gte=<val>` `?<col>__lte=<val>` 解析成
`WHERE col >= ?` / `WHERE col <= ?` 即可。`__gt` `__lt` 可以一起加。

### 2. 多键排序 `order_by=col1:desc,col2:asc`

**用例**：本地 app 默认排序是 4 键链 (priority asc → score desc → fit desc → followers desc)，
当前只能 fetch + Python 多遍稳定排序。

**建议接口**：
```
GET /api/v1/data/tk_creators?order_by=outreach_priority:asc,recommendation_score:desc
```

**实现思路**：解析逗号分隔的 `col:dir` pair，依次拼到 `ORDER BY`。

---

## P1 — 实用（中规模数据时省事）

### 3. 模糊匹配 `__like` / `__icontains`

**用例**：UI 搜索框，按 handle / bio / 推荐理由模糊匹配。当前 `?q=keyword` 太宽（所有 TEXT 列 OR），
无法定位到具体列。

**建议接口**：
```
GET /api/v1/data/tk_creators?handle__icontains=cici
GET /api/v1/data/tk_creators?bio__like=%whatsapp%
```

`__icontains` 大小写不敏感包含，`__like` 直接透传 SQL LIKE。

### 4. IN 列表 `__in=a,b,c`

**用例**：选多个推荐状态一起筛 (`recommended` + `recommended_after_review` + `low_cost_test`)。

**建议接口**：
```
GET /api/v1/data/tk_creators?recommendation_status__in=recommended,recommended_after_review,low_cost_test
```

**实现思路**：split 逗号、转成 `WHERE col IN (?,?,?)`。注意：值里如果有逗号要支持转义，
或者改用重复 query string `?col=a&col=b&col=c`。

### 5. NOT NULL / IS NULL 过滤

**用例**：筛"有邮箱"或"无邮箱"。当前用 `has_email=1` 这种 0/1 列绕过。

**建议接口**：
```
GET /api/v1/data/tk_creators?email__isnull=false
GET /api/v1/data/tk_creators?email__isnull=true
```

---

## P2 — 长期价值

### 6. 简单 JOIN / 视图

**用例**：tag 筛选、推荐历史关联、外联事件 join 达人主表。

**建议**：暂不做完整的 JOIN 引擎，但可以扩展现有的 **命名查询 (`/api/v1/queries/{name}`)**
机制，让廖这边自助 SQL。在 admin UI 加个"创建命名查询"的入口，张审核后注册。

如果觉得太开放，可以白名单几个内置 JOIN 视图：
```
GET /api/v1/views/creators_with_tags?tag_code=feminine_strong
GET /api/v1/views/creators_with_outreach?creator_handle=cicigiginana
```

### 7. WebSocket / SSE 实时推送

**用例**：多人协作时，A 改了某行，B 的 UI 自动刷新（不用手动 reload）。

**建议接口**：
```
WS  /api/v1/stream/tk_creators?since_id=130
```
连上后服务端 push 每条 INSERT/UPDATE/DELETE 的事件。客户端订阅、维护本地缓存。

---

## P3 — 安全 / 治理（独立于上面，但应该尽早做）

### 8. 内置资源 schema 锁修复

**已知问题**：之前 probe 测试发现 `POST /api/v1/tables/creators/columns` 居然返回 200，
任何持有 API key 的人都能给主表 `creator` 加列。文档里写的 403 schema 锁没生效。

**已造成的脏数据**（顺手清理一下）：
```sql
ALTER TABLE creator DROP COLUMN probe_x_a_1778226698;
ALTER TABLE creator DROP COLUMN probe_x_b_1778226698;
DROP TABLE IF EXISTS liao_keytest_20260508_155138_a;
DROP TABLE IF EXISTS liao_keytest_20260508_155138_b;
```

**建议**：在 `POST /api/v1/tables/{name}/columns` 处理函数里，先查 resource 注册表的
`is_dynamic` 字段，built-in (`is_dynamic=False`) 的资源直接返回 403。

### 9. API key 分级 / 资源粒度权限

**当前状态**：所有 key 都是全权限管理 key（probe 验证过 A 和 B 两把 key 行为完全一致），
任何人拿到 key 就能 drop / write 所有表。

**建议**：给 key 加 `scopes` 字段，至少区分 read / write / admin 三档。比如廖这边用的 key
只给到 `read:tk_*  write:tk_*` 这种范围；建表 / 改 built-in 留给 admin key。

实现层面：可以用 prefix 匹配 + 操作类型检查。无需引入完整的 RBAC 系统。

### 10. DROP TABLE / DROP COLUMN 端点

**当前缺口**：API 能建表能加列，但删不掉。所以现在数据库里堆了一些测试遗留的表
（如 `liao_keytest_*`）和列（`probe_x_*`），只能找张直接进 SQLite 删。

**建议接口**：
```
DELETE /api/v1/tables/{name}             # drop 整张动态表 (built-in 拒绝)
DELETE /api/v1/tables/{name}/columns/{col}   # drop 一列 (要求 SQLite >= 3.35)
```

加确认机制：query string 必须带 `?confirm=true` 才真删，避免误操作。

---

## 总结：建议优先级

| 优先级 | 项 | 廖这边的影响 |
|---|---|---|
| P0 | 1, 2 | 数据涨到 5K+ 时 UI 性能恢复 SQL 级 |
| P1 | 3, 4, 5 | 当前用客户端兜底；做了之后代码能简化 30% |
| P2 | 6, 7 | 跨表查询 / 多人协作场景才需要 |
| P3 | 8, 9, 10 | 安全治理，应当尽早做（与廖这边的功能解耦） |

**廖这边可以先继续推进，不阻塞**。张做完任何一项都通知一声，我把客户端的 fallback 代码删掉
（替换成原生 API 调用）即可。
