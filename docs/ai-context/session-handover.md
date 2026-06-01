# Session Handover — 2026-05-30 — 外贸部系统改造

## Task State
- **Done**：
  - Phase 1 看板与采集面板（数据地基 11 张表 + `routers/foreign_trade.py` 聚合）+ **按部门区分界面**（跨境部保留 TikTok，外贸部走招聘+社媒，按 `department_code` 切换）。
  - Phase 2 招聘端到端（`utils/job_*` 评分、`services/company_lead_service.py` 入库、`routers/company_leads.py`、前端公司客户/人才库管理页）+ Phase 2-E 招聘爬虫（`scrapers/recruitment/`，推送接 X9 ingest + 会话登录）。
  - Phase 3 小红书/抖音端到端（`utils/xhs_cleaning.py`、`services/xhs_lead_service.py` ingest+GPT judge、`routers/xhs_leads.py`、前端社媒线索页）。
  - 外贸用户端门户确认存在 + 「下载采集插件」入口（侧边栏 + 采集总览顶部卡片）。
  - **Phase 4 插件合并 + 下载按部门路由（完成）** —— 合并扩展 `desktop/foreign-trade-extension/`（recruit/ + social/ + ft_actor/ft_api_config/ft_background）；`routers/extension.py` 的 `/api/local/extension/download` 按 `department_code` 路由（foreign_trade→合并扩展、其余→TikTok）；`routers/extension_ingest_compat.py` 提供免登录 `POST /api/{companies,talents,xhs,douyin}/ingest`。已下载真实 zip 解包核对（28 文件、ft_background importScripts 根相对、依赖齐全）。
  - 全部本地 `tsc -b`+`vite build` 通过并部署到 `desktop/backend/ui/{admin,portal}`，运行中的本地 :8000 端到端验证通过。
- **下一步**：尚未 git commit/push（用户拍板后再推 GitHub → 同事服务器部署）；真机 Chrome 加载验证（本机无浏览器）；表格导入 importer/exporter UI 仍为占位；招聘批量 helper（CDP）按需移植。

## ⚠️ 验证规约（所有会话必须遵守）
**我编辑的源码目录 ≠ 用户实际拿到的产物。只看源文件不算验证完成。**
- 插件改动：以部门账号实际下载 zip → 解包 → 核对内容（manifest 引用文件存在、importScripts/side_panel 路径为根相对、改动已进包）+ `node --check`。
- 前端改动：`build` 后必跑部署脚本到 `ui/{admin,portal}` 并核对 bundle，光 build 不生效。
- 后端改动：实测运行中端点（登录态+HTTP码/返回），不靠 import 成功推断；改后端需重启 desktop。
- 详见 CHANGELOG 顶部「验证规约」与桌面 `工作留痕/外贸部改造-问题留痕记录.md`。

## 关键架构 / 部署
- **同一套部署服务跨境部+外贸部**，前端按 `department_code` 条件渲染（web 用 `useRoleStore().currentUser`，web-user 用 `useMe().user`）；外贸独立路径 `/d/collect-jobs|collect-social|ft-import|company-leads|talent-leads|social-leads`、门户 `/collect-jobs|collect-social|ft-import`。
- **usx9.us = 同事电脑作服务器**，本机 `_fresh` 是开发仓库（空 SQLite）。上线：`git push` → 同事服务器拉取 + 重建前端（`build:root/deploy:root`、`build:deploy/deploy`）+ 重启 desktop。
- 本机验证用 `localhost:8000`，账号见 `docs/外贸部改造-操作说明.md`（含 `ftuser`/外贸门户、`testadmin2`/外贸管理端）。
- 后端模型用 `create_all` 自建表（无 Alembic）；可选评分：招聘 `LLM_*`、社媒 `OPENAI_API_KEY`。

## Key Files
- 后端：`desktop/backend/models/{company_lead,talent_lead,social_lead}.py`、`services/{company_lead_service,xhs_lead_service}.py`、`utils/{job_keyword_rules,job_llm_scorer,job_exclusion,xhs_cleaning}.py`、`routers/{foreign_trade,company_leads,xhs_leads}.py`、`main.py`、`models/__init__.py`。
- 前端：`web/src/pages/department/{ForeignTradeDashboard,CollectJobs,CollectSocial,CompanyLeads,TalentLeads,SocialLeads,ForeignTradeImport}.tsx`、`web-user/src/pages/{ForeignTradeBusiness,ForeignTradeCollection,CollectJobs,CollectSocial,ForeignTradeImport}.tsx`、两套 `layouts/{menus.ts,Sidebar.tsx}`、`api/foreignTrade.ts`、各 `routes.tsx`/`App.tsx`。
- 爬虫：`scrapers/recruitment/`。
- 源系统：`F:\Claude_Project\CompanyLeads`、`F:\Claude_Project\x9_xhs_douyin_complete_deploy_20260530_121224`。

## Open Questions
- Phase 4 扩展合并后，下载按钮下发的应是合并扩展（当前仍是 TikTok 扩展）。
- 表格导入（CollectImport/ForeignTradeImport）目前为占位，正式导入 UI/接口（importer/exporter）未做。
