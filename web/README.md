# X9 跨境数据库 · 前端静态预览

3 个管理员角色 × 24 个页面的静态预览原型,基于 Vite + React 18 + TypeScript + Tailwind CSS + ECharts。

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

## 3 个角色 × 24 页

页面通过路径前缀划分,右上角"角色切换器"可在三个角色间切换,侧边栏菜单随之变化。

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
- **Mock**: 内置 `src/mock/*.ts`,无需后端 API

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
│   ├── mock/                   # department / company / super 三套 mock
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

## Mock 数据来源

- **部门管理员**:数字与参考截图严格对齐(总达人 33、已推荐 17、待审核 6 等)
- **公司管理员**:30 日 GMV ¥2.46M、6 部门、Top 10 SKU、近 90 天三条增长曲线
- **超级管理员**:24h 请求、慢查询、用户与 Key、Provider 配置、命名查询等

修改 mock 文件即可联调或微调展示数据。

## 后端联调(后续步骤)

当前完全静态,所有数据从 `src/mock/*.ts` 导入。要切换到真实 API:

1. 新建 `src/api/client.ts` 封装 fetch + X-API-Key
2. 把页面里的 `import { ... } from '@/mock/...'` 改成 TanStack Query hooks
3. `vite.config.ts` 中加 `server.proxy` 把 `/api` 转发到 FastAPI 18765 端口

后端 API 不需要任何修改 — `/api/v1/data/{resource}`、`/api/v1/queries/*`、`/api/v1/llm/complete` 均已支持。
