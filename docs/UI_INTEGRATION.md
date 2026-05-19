# X9 前端接入 + 数据库支撑文档

本文档记录两个新 React 前端项目接入 X9 系统的完整改动,以及为支撑新 UI 添加的数据库表。

## 一、前端项目部署位置

| 项目 | 路径 | 后端 | 访问 URL |
|---|---|---|---|
| **web/** (管理端 · 4 角色 × 24 页) | `F:\X9_AI_system\web\` | core / FastAPI :18765 | http://localhost:18765/**web-preview/** |
| **web-user/** (用户端 · 8 页) | `F:\X9_AI_system\web-user\` | desktop / FastAPI | https://usx9.us/**portal/** |

### 部署到生产

```powershell
# 管理端
cd F:\X9_AI_system\web
scripts\build-deploy.bat
# 产物 → core/app/static/web-preview/

# 用户端
cd F:\X9_AI_system\web-user
scripts\build-deploy.bat
# 产物 → desktop/backend/ui/portal/
# 注:需要重启 desktop backend 才能加载 /portal/ 路由
```

### 共存策略(无侵入)

| 老路径 | 状态 |
|---|---|
| `/` (老 UI index.html) | 完全不动,可继续访问 |
| `/login`, `/admin/`, `/workspace/cross-border/` | 完全不动 |
| `/api/v1/*`, `/api/local/*` | 完全不动,廖的爬虫不变 |
| `/static/*`, `/ui/*` | 完全不动 |
| `/web-preview/`, `/portal/` | ★ 新增,React UI |

Chrome 插件、Electron 桌面壳、爬虫脚本 — 全部不需要任何修改。

---

## 二、数据库改动

### core/ (SQLite) — `migrate_v18_ui_support.py`

新增 5 张表 + creator/staff/outreach 各新增 `department_id` 字段(已 backfill)。

| 表 | 用途 | UI 页 | 当前行数 |
|---|---|---|---|
| `department` | 公司/部门组织树 | 全局(4 角色架构基础)| **4**(已种入:跨境/外贸/选品/运营) |
| `api_metric` | 端点调用统计(日/小时桶) | A8 API 统计 | 0(等真实流量写入) |
| `llm_token_usage` | LLM Token 消耗(Provider × Model × Feature × 日) | A3 LLM 配置 | 0(等 LLM 调用写入) |
| `business_metric_daily` | 日 KPI 快照(C 系列看板加速) | C1-C8 公司管理员 | 0(等 daily job 写入) |
| `notification` | 应用内通知(铃铛) | 全局 TopBar | **3**(种入示例通知) |

**额外字段**:
- `creator.department_id` — 132 行已 backfill = 1 (cross_border)
- `staff.department_id` — 8 行已 backfill
- `outreach.department_id` — 101 行已 backfill

**注册资源**:5 张表都已写入 `_meta_resource`,通过 `/api/v1/data/{name}` 可直接 CRUD:
- `/api/v1/data/departments` ✓
- `/api/v1/data/webhooks` ✓ (原 webhook_subscriber,resource 名为 webhooks)
- `/api/v1/data/notifications` ✓
- `/api/v1/data/api_metrics` ✓
- `/api/v1/data/llm_token_usages` ✓
- `/api/v1/data/business_metrics_daily` ✓

### desktop/backend/ (PostgreSQL) — `002_ui_support.py`

新增 3 张表(方言自适应,SQLite/PG 都兼容)。

| 表 | 用途 | UI 页 |
|---|---|---|
| `assistant_conversations` | AI 助手会话(刷新前的多轮记忆)| /portal/assistant |
| `assistant_messages` | 每条 user/assistant 消息 + token 用量 | /portal/assistant |
| `keyword_today_trend` | 24h 采集小时桶(观察/达人/推荐/审核计数)| /portal/collection 趋势曲线 |

### 重新运行迁移

```powershell
# core/
cd F:\X9_AI_system\core
py scripts\migrate_v18_ui_support.py

# desktop/
cd F:\X9_AI_system
py -3.11 -m desktop.backend.migrations.002_ui_support
```

两个迁移都是**幂等的** — 多次运行不会重复创建或破坏数据。

---

## 三、后端代码侵入

**只有两处轻微改动**,都加在文件末尾,不影响现有逻辑:

### core/app/main.py
```python
# 已添加 (133-154 行)
@app.get("/web-preview")        # → 重定向 /web-preview/
@app.get("/web-preview/")       # → index.html
@app.get("/web-preview/{full_path:path}")  # → SPA fallback
```

### desktop/backend/main.py
```python
# 已添加 (139-165 行)
@app.get("/portal")             # → 重定向 /portal/
@app.get("/portal/")            # → index.html
@app.get("/portal/{full_path:path}")  # → SPA fallback (登录验证由 main.py 既有中间件处理)
```

---

## 四、UI 字段映射(规避踩坑)

迁移期发现的字段名差异,**已修复**:

| UI 之前 | 真实 DB | 实际使用 |
|---|---|---|
| `webhook_subscriber` (404) | `webhooks` resource | ✓ |
| `audit_log.user_id` | `audit_log.operator` | ✓ |
| `audit_log.changes_json` | `audit_log.changes` | ✓ |
| 自创 priority P1-P4 | `creator.outreach_priority` | UI 从真实字段聚合,无 mock 回退 |

---

## 五、Dev 体验

管理端 `web/` 已取消 dev-mode mock fallback:
- `/api/local/auth/*` 必须返回真实登录会话
- `/api/v1/*` 必须走 desktop → core → PostgreSQL
- 接口失败会直接显示错误,不会用假数据把页面撑起来

```powershell
# 管理端 dev
cd web && npm run dev  # http://localhost:5173/

# 用户端 dev  
cd web-user && npm run dev  # http://localhost:5174/
```

---

## 六、下一步可选优化

| 优化 | 落地路径 |
|---|---|
| **API 调用埋点** | 在 `core/app/main.py` 加 middleware,记录到 `api_metric` 表 |
| **LLM 用量埋点** | 在 `core/app/llm.py` 的 `/llm/complete` 包装层写 `llm_token_usage` |
| **业务日快照** | 加 `scripts/snapshot_daily.py`,每日 0 点跑 cron 写 `business_metric_daily` |
| **AI 对话持久化** | `desktop/backend/routers/shared.py` 的 assistant_chat 改成读写 `assistant_conversations/messages` |
| **通知中心** | `TopBar` 加铃铛点击展开,调 `/api/v1/data/notifications?recipient=*&read_at=null` |

---

## 七、验证状态(2026-05-15)

```
core 后端 (:18765)
  ✓ /api/v1/data/departments       4 rows (seeded)
  ✓ /api/v1/data/webhooks          0 rows (waiting for config)
  ✓ /api/v1/data/notifications     3 rows (seeded)
  ✓ /api/v1/data/api_metrics       0 rows (waiting for traffic)
  ✓ /api/v1/data/llm_token_usages  0 rows (waiting for LLM calls)
  ✓ /api/v1/data/business_metrics_daily  0 rows (waiting for daily job)
  ✓ /api/v1/data/creators?limit=1  132 rows total (backfilled department_id)

desktop 后端 (:8000)
  ✓ assistant_conversations        0 rows
  ✓ assistant_messages             0 rows
  ✓ keyword_today_trend            0 rows
```
