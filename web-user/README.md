# X9 用户端 (Portal) · React 重构

替换 `desktop/backend/ui/index.html` (vanilla JS, 32KB + app.js 141KB) 的 React 重构版本,**线上对应 https://usx9.us/workspace/cross-border/**。

技术栈与设计与 `web/`(管理端)一致:Vite + React 18 + TypeScript + Tailwind + ECharts + TanStack Query。
**深色主题**默认(与现有 desktop UI 一致),日间主题可切换。

## 8 个页面 · 完全镜像现有 IA

| 路径 | 页面 | 数据来源 |
|---|---|---|
| `/business` | 业务看板 | `/api/local/admin/business-dashboard` |
| `/dashboard`(默认) | 仪表盘 | `/api/local/app/status` + `/db/stats` + `/extension/status` |
| `/collection` | 采集监控 | `/api/local/extension/status` + `/run-progress` |
| `/recommendations` | 推荐列表 | `/api/local/creators/recommended` |
| `/review` | 人工审核 | `/api/local/review-tasks?status=pending` |
| `/export` | 导出/导入 | `/api/local/export/*` + `/import/creators` |
| `/hotkw` | TikTok 热搜 | `/api/local/shared/keywords/dashboard` |
| `/assistant` | AI 助手 | `/api/local/shared/assistant/{info,chat}` |

## 部署与访问

```bash
cd F:\X9_AI_system\web-user
npm install          # 一次性
npm run build:deploy # 构建到 dist-deploy/ (base = /portal/)
npm run deploy       # 复制到 desktop/backend/ui/portal/

# 或一键:
scripts\build-deploy.bat
```

**生效需要重启 desktop backend**(因为现行启动命令未带 `--reload`):

```bash
# 停止旧进程后:
cd F:\X9_AI_system
线上入口统一使用 https://usx9.us
# 或使用现有脚本(会自动打开浏览器):
desktop\start_desktop.bat
```

访问:**https://usx9.us/portal/**

## 与现有 UI 的关系

| 路径 | 内容 | 状态 |
|---|---|---|
| `/` | 老 landing.html | 完全不动 |
| `/login` | 老 login.html | 完全不动 |
| `/workspace/cross-border/` | 老 vanilla JS UI (index.html + app.js) | **完全不动**,继续可用 |
| `/admin/` | 老 admin.html | 完全不动 |
| `/api/local/*` | 所有 API | 完全不动 |
| `/ui/*` | 静态文件 mount | 完全不动 |
| **`/portal/`** | **新 React UI** | **新增** |

Chrome 插件、`/api/local/extension/*` 心跳协议等完全保持。

## 鉴权

React app 使用 `credentials: 'include'`,沿用现有 cookie 会话(`SESSION_COOKIE`)。
- 未登录访问任何 `/portal/*` 页面 → 自动跳转 `/login?next=...`
- 登录后回到 `/portal/dashboard`

## 开发

```bash
cd web-user
npm run dev   # dev proxy /api/local -> https://usx9.us
```

Vite dev server 会把 `/api/local/*` 代理到 desktop backend(8000),携带 cookie。

## 关键文件

```
web-user/
├── src/
│   ├── main.tsx, App.tsx
│   ├── layouts/{AppShell, Sidebar, TopBar, menus.ts}
│   ├── api/{client.ts, endpoints.ts, types.ts, queryClient.ts}
│   ├── hooks/useApi.ts          ← 12 个 hook 覆盖所有端点
│   ├── stores/uiStore.ts        ← 主题、侧栏、语言
│   ├── components/
│   │   ├── kpi/KpiCard.tsx
│   │   ├── charts/{EChart, ChartCard}.tsx
│   │   ├── table/DataTable.tsx
│   │   └── states/States.tsx    ← Loading / Error / Empty
│   ├── lib/{cn, format, chart-defaults}.ts
│   └── pages/                   ← 8 个页面
│       ├── Business.tsx
│       ├── Dashboard.tsx        ← 默认页
│       ├── Collection.tsx
│       ├── Recommendations.tsx
│       ├── Review.tsx
│       ├── ExportImport.tsx
│       ├── HotKeywords.tsx
│       └── Assistant.tsx
├── scripts/{deploy.mjs, build-deploy.bat}
├── package.json, vite.config.ts, tailwind.config.ts
```

## 设计 token

```css
/* 镜像 desktop/backend/ui/theme.css 深色主题 */
--bg:         #0b0d12  (深蓝黑)
--bg-elev-1:  #12161e  (卡片)
--bg-elev-2:  #181e2a  (悬浮)
--accent:     #06b6d4  (青蓝)
--good/warn/bad: 与现有一致
```

## 仍是占位 / 待完善

| 页面 | 备注 |
|---|---|
| Business | `/admin/business-dashboard` 可能需 admin 角色,普通用户看到空状态 |
| Collection | 24h 采集趋势依赖后端返回 `today_trend`,目前如无则不显示 |
| Assistant | AI 历史不持久化(刷新即清空,跟原版一致) |
