# X9 跨境数据库 · 前端预览

3 个管理角色 × 24 个页面,基于 Vite + React 18 + TypeScript + Tailwind CSS + ECharts。
**已全量接通真实后端 API**,管理端数据来自登录会话保护的 PostgreSQL `/api/v1/*`。

## 快速开始

```bash
cd F:\X9_AI_system\web

# 一次性安装依赖(已安装可跳过)
npm install

# 开发态启动
npm run dev
# 浏览器打开 http://localhost:5173

# 生产构建
npm run build

# 本地预览构建产物
npm run preview
```

## 3 个管理角色 × 24 页

页面通过路径前缀划分,实际入口由后端登录会话角色决定,前端不允许切换身份。

### 部门管理员 `/d/*`(默认进入)

参考截图样式 1:1 还原,8 个业务模块。

| 路径 | 页面 |
|---|---|
| `/d/dashboard` | 数据看板(★对齐参考图) |
| `/d/creators` | 达人管理 |
| `/d/leads` | 线索管理 |
| `/d/emails` | 邮件管理 |
| `/d/samples` | 样品管理 |
| `/d/videos` | 视频管理 |
| `/d/products` | 产品管理 |
| `/d/settings` | 设置中心 |

### 公司管理员 `/c/*`(老板视角)

| 路径 | 页面 |
|---|---|
| `/c/overview` | 公司业绩总览 |
| `/c/revenue` | 营收与利润 |
| `/c/departments` | 部门绩效对比 |
| `/c/growth` | 增长趋势 |
| `/c/funnel` | 全公司转化漏斗 |
| `/c/products` | SKU 价值地图 |
| `/c/creators` | 达人资产总览 |
| `/c/events` | 重要事件时间线 |

### 超级管理员 `/a/*`(系统运维)

| 路径 | 页面 |
|---|---|
| `/a/monitor` | 系统监控 |
| `/a/users` | 用户与权限 |
| `/a/llm` | LLM 配置中心 |
| `/a/webhooks` | Webhook 集成 |
| `/a/audit` | 审计日志 |
| `/a/resources` | 资源浏览器 |
| `/a/queries` | 命名查询 |
| `/a/api-stats` | API 调用统计 |

## 技术栈

- **构建**: Vite 5 + TypeScript 5
- **框架**: React 18 + React Router 6
- **样式**: Tailwind CSS 3
- **图表**: Apache ECharts 5
- **状态**: Zustand 4
- **表格**: TanStack Table 8(headless,自封 DataTable)
- **图标**: lucide-react
- **数据**: 真实 `/api/v1/*` 接口,开发态不再回退 mock

## 目录结构

```
web/
├── public/
├── src/
│   ├── main.tsx, App.tsx       # 入口 + 路由
│   ├── layouts/                # AppShell / Sidebar / TopBar / menus.ts
│   ├── components/
│   │   ├── kpi/                # KpiCard
│   │   ├── charts/             # EChart + ChartCard
│   │   ├── table/              # DataTable
│   │   ├── progress/           # PriorityBar
│   │   ├── role/               # RoleSwitcher
│   │   └── Pill.tsx, PageHeader.tsx
│   ├── stores/                 # roleStore (zustand)
│   ├── pages/
│   │   ├── department/         # D1-D8 + routes.tsx
│   │   ├── company/            # C1-C8 + routes.tsx
│   │   └── super/              # A1-A8 + routes.tsx
│   ├── lib/                    # colors / format / chart-defaults / cn
│   └── styles/index.css        # Tailwind + 自定义组件类
├── package.json, vite.config.ts, tailwind.config.ts, tsconfig.json
```

## 风格规范

- 主蓝 `#3370ff`、状态机 9 色、Tier 5 色见 `src/lib/colors.ts`
- 侧边栏深色 `#1f1f2e`,选中态橙色 `#fef3eb` + 4px 左侧条 `#f97316`
- KPI 卡淡色圆形图标(10 套预设色 `kpiIconBg` / `kpiIconFg`)
- 字号 11-26px,行高 1.5,圆角 4-10px,卡片 padding 12-16px
- 数字 tabular-nums(`.num` 类)

## 数据接入

所有 24 页已经全量接入真实 API,**无 mock 残留**。

- **资源 CRUD**: `/api/v1/data/{resource}` (creators / products / outreach / categories / staff / audit_log / keyword_snapshots / outreach_example)
- **命名查询**: `/api/v1/queries/{name}` (D3 线索池用 `creators_to_contact`)
- **元信息**: `/api/v1/version`, `/api/v1/resources`, `/api/v1/queries` (超管页用)
- **用户与 LLM**: `/api/v1/auth/users`, `/api/v1/llm/providers`

API 客户端在 [src/api/client.ts](src/api/client.ts),hooks 在 [src/hooks/useApi.ts](src/hooks/useApi.ts),
聚合工具(漏斗、Tier 分布、BD 战绩等前端聚合)在 [src/lib/derive.ts](src/lib/derive.ts)。

## 集成方式

挂到 FastAPI `/web-preview/` 子路径,与现有 `/`、`/api/*`、`/static/*` 并存,廖的爬虫脚本零修改。
路由配置见 [core/app/main.py:133-154](../core/app/main.py)。

```powershell
# 一键构建并部署到后端
cd web
scripts\build-deploy.bat
# 浏览器打开 http://localhost:18765/web-preview/
```

## 仍是示意的部分

- **A1 系统监控**:CPU/内存/磁盘仪表盘是示意值(后端暂无 metrics 端点)
- **A4 Webhook**:`webhook_subscriber` 表未创建(404),显示空状态 + 引导
- **A8 API 统计**:列出真实端点清单,但调用量/耗时/错误率需后端 metrics
