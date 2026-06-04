# X9 系统边界与全链路验收

> 本文用于交接、部署和验收。它只描述当前系统的主线边界、功能模块、API 归属和检查步骤，不改变任何业务行为。

## 1. 当前主线

| 模块 | 当前定位 | 运行/部署说明 |
|---|---|---|
| `desktop/` | 主后端与运行入口 | FastAPI 运行在 `:8000`，负责登录、权限、门户静态资源、采集接入、推荐、建联、外贸线索和统计。 |
| `web/` | 管理后台源码 | React/Vite 源码，服务 `/`、`/a/*`、`/c/*`、`/d/*`、`/preview/*`，构建后部署到 `desktop/backend/ui/admin/`。 |
| `web-user/` | 员工门户源码 | React/Vite 源码，服务 `/portal/*`，构建后部署到 `desktop/backend/ui/portal/`。 |
| `core/` | Core 数据与 AI 中心 | FastAPI 运行在 `:18765`，保留产品库、LLM、AI 助手、通用 `/api/v1` 数据资源和旧业务中心。 |
| `scrapers/` | 独立采集工具 | 命令行或小型 Web UI 工具，输出 CSV/JSON 或对接后端。 |
| `infra/` | 基础设施脚本 | PostgreSQL、备份、恢复、本地/远程启动和部署脚本。 |
| `tools/` | 维护工具 | smoke test、数据库检查、schema diff、同步和一次性诊断。 |
| `x9_creator_desktop_system/` | 兼容/历史包 | 不作为新功能主线；仅在测试、旧脚本或兼容导入仍依赖时保留。 |

共享数据层是 PostgreSQL：`localhost:15432/x9db`。线上入口 `https://usx9.us` 通常指向 `desktop` 后端。

## 2. 功能模块

| 功能模块 | 主要实现 | 说明 |
|---|---|---|
| 认证与权限 | `desktop/backend/routers/auth.py`、`services/auth_service.py` | Cookie session、注册审批、改密、用户管理、角色跳转和部门范围控制。 |
| 管理后台 | `web/` + `desktop/backend/ui/admin/` | 超管、公司管理员、部门管理员和预览页面。 |
| 员工门户 | `web-user/` + `desktop/backend/ui/portal/` | 部门用户工作台、采集、推荐、建联、数据工具和 AI 助手入口。 |
| Chrome 采集插件 | `desktop/chrome-extension/`、`routers/extension.py`、`routers/collector.py` | TikTok Shop/X9 线索采集、heartbeat、worker 绑定、命令轮询、运行进度。 |
| 达人数据 | `routers/creators.py`、`models/creator.py` | 达人列表、详情、领取、释放、分配和多维筛选。 |
| 评分与推荐 | `services/scoring_engine.py`、`tag_engine.py`、`recommendation_engine.py`、`pipeline.py` | 评分、标签、推荐队列、人工审核任务生成。 |
| 人工审核 | `routers/review_tasks.py`、`services/review_task_service.py` | 推荐前风险复核、审核状态更新和后续队列回流。 |
| 建联与 Gmail | `routers/outreach.py`、`services/outreach_service.py`、`gmail_service.py`、`gmail_sync_service.py` | 模板、预览、草稿、发送、归档、回复同步、建联锁和产品素材。 |
| 外贸线索 | `routers/foreign_trade.py`、`company_leads.py`、`xhs_leads.py` | 公司线索、人才线索、小红书/抖音社媒线索、清洗、GPT 判断和跟进。 |
| 外贸采集插件 | `desktop/foreign-trade-extension/`、`desktop/foreign-trade-helper/` | 招聘网站、小红书、抖音采集和 native/CDP 辅助链路。 |
| 看板与统计 | `routers/dashboard.py`、`analytics.py`、`admin.py`、`services/unified_dashboard_service.py` | 部门、公司、超管、采集、外贸、API 和系统指标。 |
| 导入导出 | `routers/imports.py`、`export.py`、`services/export_service.py` | 表格导入模板、达人导入和推荐达人导出。 |
| Core 产品/AI | `core/app/main.py`、`llm.py`、`agent.py`、`outreach_ai.py`、`keyword_ai.py` | 产品库、通用数据资源、命名查询、LLM、AI 助手、标题/话术/关键词能力。 |
| Electron 外壳 | `desktop/desktop/` | 启动/守护后端并打开桌面窗口；同一系统也可直接用浏览器访问。 |

## 3. API 边界

| API 前缀 | 所属系统 | 用途 |
|---|---|---|
| `/api/local/*` | `desktop` 主系统 | 登录、采集、达人、推荐、建联、外贸、统计、导入导出、插件控制。 |
| `/api/v1/*` | `desktop` 代理到 `core` | 通用资源 CRUD、命名查询、Core 数据和部分管理后台数据。 |
| `/api/v2/*` | `desktop` 新/预览接口 | v2 预览页的数据接口。 |
| `/api/{companies,talents,xhs,douyin}/ingest` | `desktop` 插件兼容入口 | 外贸采集插件或 helper 的兼容写入入口。 |
| `/api/products`、`/api/creators`、`/api/outreach` | `core` 旧业务接口 | Core 旧产品库、达人主数据和建联流水接口。 |

约束：

- 不在整理性修复里新增、删除或重命名 API。
- 不改变请求/响应结构。
- 不改变前端路由、菜单、布局、颜色、交互或页面可见文案。
- 不改变数据库表、字段、索引或迁移逻辑。

## 4. 构建与部署规则

前端源码变更不会自动影响线上页面，必须构建并部署到 `desktop/backend/ui/`：

```powershell
# 管理后台: /, /a/*, /c/*, /d/*, /preview/*
cd F:\X9_AI_system\web
npm run build:root
npm run deploy:root

# 员工门户: /portal/*
cd F:\X9_AI_system\web-user
npm run build:deploy
npm run deploy
```

后端源码变更后必须重启 `desktop` 后端。仅修改 Markdown 文档通常不需要重启服务。

插件变更必须额外验证真实下载包：

1. 用对应部门账号调用 `/api/local/extension/download`。
2. 解压下载的 zip。
3. 核对 `manifest.json` 引用的文件都存在。
4. 对关键 JS 执行 `node --check`。

## 5. 验收清单

### 本地自动化

```powershell
cd F:\X9_AI_system
py -3.11 -m pytest desktop\backend\tests -q

cd F:\X9_AI_system\web
npm run build

cd F:\X9_AI_system\web-user
npm run build
```

### 本地服务 smoke

```powershell
cd F:\X9_AI_system
.\infra\scripts\db_init.ps1
.\start_all.ps1
```

检查：

- `http://localhost:18765`
- `http://localhost:8000/health`
- `http://localhost:8000/login`
- `http://localhost:8000/`
- `http://localhost:8000/portal/`
- `http://localhost:8000/api/local/auth/me`
- `http://localhost:8000/api/local/dashboard/unified`

### 线上 smoke

线上验证需要测试账号。若没有测试账号，只能验证公开链路。

检查：

- `https://usx9.us/health`
- `https://usx9.us/login`
- 登录后可访问对应角色主页：
  - 超管：`/a/dashboard`
  - 公司管理员：`/c/overview`
  - 部门管理员：`/d/dashboard`
  - 部门用户：`/portal/`
- 插件下载接口：`/api/local/extension/download`
- 主要只读 API：
  - `/api/local/dashboard/unified`
  - `/api/local/foreign-trade/dashboard`
  - `/api/local/recommendations`
  - `/api/local/outreach/tracking`

线上 smoke 不发送真实邮件、不执行真实批量采集、不写入业务数据。

## 6. 验收记录模板

```text
日期:
提交/分支:
执行人:
环境: 本地 / 线上

自动化:
- desktop pytest:
- web build:
- web-user build:

本地 smoke:
- core health/root:
- desktop health:
- login page:
- admin SPA:
- portal SPA:
- auth/me:
- dashboard/unified:

线上 smoke:
- public health:
- login:
- role routes:
- extension download:
- dashboard APIs:
- recommendations/outreach:

受限项:
- 例如: 未提供测试账号,因此未覆盖登录后角色页面。

失败项:
- 问题:
- 影响:
- 分类: 文档整理问题 / 需下一轮功能修复的问题
- 证据:
- 建议下一步:
```
