# X9 AI System

> X9 跨境电商达人建联全流程系统(本地开发版)

## 这是什么

一套面向 TikTok / YouTube 达人建联的内部系统,涵盖 **数据库 → AI 内容生成 → 抓取 → 评分推荐 → 邮件外联** 的完整闭环。

当前主运行系统由多个独立但共享同一个 PostgreSQL 数据库的组件组成:

| 组件 | 路径 | 端口 | 职责 |
|------|------|------|------|
| **Desktop** | `desktop/` | `:8000` | 当前主后端和运行入口:登录权限、门户静态资源、扩展接入、Gmail 邮件外联、评分推荐、外贸线索和统计 |
| **Web Admin** | `web/` | 构建产物 | 管理后台源码,部署到 `desktop/backend/ui/admin/`,服务 `/`、`/a/*`、`/c/*`、`/d/*`、`/preview/*` |
| **Web Portal** | `web-user/` | 构建产物 | 员工门户源码,部署到 `desktop/backend/ui/portal/`,服务 `/portal/*` |
| **Core** | `core/` | `:18765` | 产品库、达人主数据、通用 `/api/v1`、LLM 接入中心、AI 文案/Agent 聊天和旧业务中心 |
| **Scrapers** | `scrapers/` | — | 命令行抓取工具(YouTube 邮箱、TikTok 个人页),输出 CSV/JSON |
| **Legacy Compat** | `x9_creator_desktop_system/` | — | 兼容/历史包,不作为新功能主线 |

数据库:**PostgreSQL 16** 在 Docker 容器 `x9-postgres@localhost:15432/x9db`。

## 快速开始(本地)

```powershell
# 第一次设置:确保 postgres 容器在跑
.\infra\scripts\db_init.ps1

# 一键启动 PostgreSQL + desktop
.\start_all.ps1

# 如需 /api/v1 或 Core 产品库页面,额外启动 Core
.\start_all.ps1 -StartCore
```

浏览器自动打开 `http://localhost:18765`(Core 的产品/达人/建联管理界面)。
Desktop / Portal 统一访问 `https://usx9.us`。本地开发时 Desktop 后端也可通过 `http://localhost:8000` 访问。

## 目录结构

```
F:\X9_AI_system\
├── core/              ← 业务数据与 AI(原 F:\Database)
│   ├── app/           FastAPI :18765 服务代码
│   ├── scripts/       数据迁移、导入导出
│   └── database.db    SQLite(过渡用,见下文)
├── desktop/           ← 桌面应用(原 Auto boker grab\x9_creator_desktop_system)
│   ├── backend/       FastAPI :8000 服务代码
│   ├── chrome-extension/   Chrome 扩展 + relay 适配器
│   ├── desktop/       Electron 外壳
│   └── data/          (本地配置,SQLite 已弃用为冷备)
├── web/               ← 管理后台 React/Vite 源码,部署到 desktop/backend/ui/admin/
├── web-user/          ← 员工门户 React/Vite 源码,部署到 desktop/backend/ui/portal/
├── scrapers/          ← 抓取工具(原 Auto boker grab 顶层)
│   ├── webui.py            YouTube 抓取的 Flask UI
│   ├── youtube_email_grabber.py
│   └── tiktok_profile_filter.py
├── tools/             ← 跨项目工具(x9_smoke_test, x9_creator_db_check 等)
├── infra/             ← 基础设施
│   ├── docker/docker-compose.yml   x9-postgres 容器定义
│   └── scripts/                   db_init/db_backup/db_restore + 部署脚本
├── archive/extensions/ ← v1.0.19 扩展归档
├── docs/              ← 文档(架构、部署、schema、回滚)
├── x9_creator_desktop_system/ ← 兼容/历史包
├── .env.shared        ← 共享配置(各子项目可覆写)
├── start_all.ps1      ← 一键启动
└── README.md
```

## 详细文档

- [`docs/architecture.md`](docs/architecture.md) — 各组件交互、端口、数据流
- [`docs/system_boundary_and_acceptance.md`](docs/system_boundary_and_acceptance.md) — 当前主线边界、功能模块、API 归属、构建部署和验收清单
- [`docs/deployment_local.md`](docs/deployment_local.md) — 从零到能用
- [`docs/schema_unified.md`](docs/schema_unified.md) — 数据库统一后的表清单
- [`docs/rollback.md`](docs/rollback.md) — 出问题时怎么回退
- [`scrapers/README.md`](scrapers/README.md) — 抓取工具如何把数据喂回数据库

## 本次合并(2026-05-11)做了什么

之前是两个独立的项目目录(`F:\Database\` 和 `F:\X9_AI_system\Auto boker grab\`),本次:

1. 物理上合并为一个根目录 `F:\X9_AI_system\`
2. 数据库统一到 PostgreSQL(原本 desktop 已经在用,core 同步)
3. 把 A(原 F:\Database)的 132 条 `creator` 记录合并进 B(desktop)的 `creators` 表(166 条)
4. 写了 `start_all.ps1` 一键启动 + `infra/docker/docker-compose.yml` 接管 postgres 容器
5. 备份了一切到 `F:\backup\`(pg_dump + 完整目录快照)

完整方案见 `docs/architecture.md` 和 `docs/rollback.md`。

## 已知遗留(下一阶段处理)

- **`core/app/v1.py` 的后端来源由配置决定**。当前默认走 PostgreSQL,但仍保留 SQLite fallback 和 `core/database.db` 兼容旧流程。
- **`core/.venv` 是从 F:\Database 搬过来的旧虚拟环境,路径已失效**。需要 Python 环境时新建。
- **`creator` 旧表保留,未 rename**。所有读路径(main.py / pg_dashboard.py 等)仍在读它,等 v1.py 移植完成后再做这步。
- **生产实例 192.168.1.171 本次不动**,等本地稳定后单独制定迁移方案。
