# 系统架构

## 三个组件,一个数据库

```
                ┌───────────────────────────────────────────────┐
                │  PostgreSQL :15432  (容器 x9-postgres)         │
                │  数据库 x9db,42 张表                          │
                │  ┌─────────────────────────────────────────┐  │
                │  │ creators(166)— 达人主表(统一后)        │  │
                │  │ creator (132)— A 旧主表(legacy 只读)    │  │
                │  │ tk_creators(164)— 廖的 lead pool 镜像   │  │
                │  │ product(44), outreach(101), ...           │  │
                │  │ raw_observations(1914)— 扩展观察记录    │  │
                │  └─────────────────────────────────────────┘  │
                └─────────────▲──────────────▲──────────────────┘
                              │              │
            ┌─────────────────┼──────────────┼─────────────────┐
            │                 │              │                 │
       ┌────▼──────┐    ┌─────▼──────┐  ┌────▼──────┐   ┌──────▼─────┐
       │   Core    │    │  Desktop   │  │ Scrapers  │   │  Chrome    │
       │  :18765   │    │   :8000    │  │  (CLI)    │   │  Extension │
       │           │    │            │  │           │   │            │
       │ • 产品库  │    │ • 桌面 UI  │  │ • YouTube │   │ • TK DOM   │
       │ • 达人 UI │    │ • 扩展接入 │  │ • TikTok  │   │   抓取     │
       │ • 建联   │    │ • 评分推荐 │  │   (输出   │   │ • POST 给  │
       │ • LLM Hub │    │ • Gmail   │  │   CSV/    │   │   desktop  │
       │ • AI 文案 │    │   外联     │  │   JSON)   │   │   :8000    │
       │ • Agent  │    │ • 审核任务 │  │           │   │            │
       └───────────┘    └────────────┘  └───────────┘   └────────────┘
            ▲                                ▲
            │                                │
       廖的爬虫                          手工运行
       (HTTP API)                       (脚本)
```

## 端口分配

| 端口 | 谁在听 | 协议 |
|------|--------|------|
| 15432 | PostgreSQL(容器 x9-postgres) | PostgreSQL |
| 18765 | Core FastAPI | HTTP |
| 8000  | Desktop FastAPI | HTTP |
| 8765  | scrapers/webui.py(YouTube 抓取 UI) | HTTP(可选,手起) |

## 数据流

### 入站(写入)
- **Chrome 扩展 → Desktop**:用户在 TikTok 上浏览时,扩展 DOM 抓取 → relay 转格式 → `POST :8000/api/local/extension/x9-compat/ingest-creators` → 写 `creators` + `raw_observations`。
- **廖的爬虫 → Core**:`POST :18765/api/v1/data/tk_creators/bulk`(目前仍写 SQLite,见"已知遗留")。
- **手工导入**:`core/scripts/import_*.py` 一次性把 Excel 数据塞 SQLite/postgres。
- **Scrapers**:目前 **没有** 直接入库,只输出 CSV/JSON(见 `scrapers/README.md`)。

### 出站(读取)
- **Core UI / 廖的爬虫读 Core**:`GET :18765/api/v1/data/<resource>` 或 `/api/products` 等。
- **Desktop UI / Electron 读 Desktop**:`GET :8000/api/local/*`。
- **跨进程一致性**:两个后端读同一个 PostgreSQL,所以任何一边写完,另一边立即可见。**前提**是写路径已迁到 postgres。

## 认证

| 服务 | 认证方式 | 谁来访 |
|------|----------|--------|
| Core (`/api/v1/*` 写操作) | API Key(SHA-256 hash + 范围/scope) | 廖、张、其他外部系统 |
| Desktop (`/api/local/*`) | JWT cookie session + 部门权限 + 注册审批 | 业务部门员工(浏览器/Electron) |

两套认证目前**不互通**。一个用户要同时操作两边需要两套凭证。统一是后续任务(单独的工作量)。

## 共享数据库的好处

- 同一条 creator 数据在两边可见,无需双写或同步
- 改 schema 只改一处(PostgreSQL ALTER TABLE)
- 备份只备一处(`infra/scripts/db_backup.ps1`)
- 跨服务的报表/分析查询可以 join

## 共享数据库的代价

- 任何 schema 变更影响双方。要在 `core/scripts/migrate_v*.py` 写迁移并保持幂等。
- 字段命名要协调:已知 `creators` 表里同时有 A 风格(`current_status`)和 B 风格(`followers_count`)字段。
- 部署难度:任何"全量重置"都得双方都同意。
