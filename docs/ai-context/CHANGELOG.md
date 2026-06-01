# CHANGELOG — 外贸部系统改造

> 记录外贸部（招聘线索 + 小红书采集）改造的逐次变更。格式：`+` 新增 / `~` 修改 / `-` 移除 / `#` 说明。全部为 2026-05-30 起，按从新到旧排列。

## 修复 + 批量采集真实评估（2026-06-01）

- `~` Fixed: 合并插件 `recruit/background.js` 的 `backendUrl` 默认值 `127.0.0.1:8002`（CompanyLeads 后端）→ `127.0.0.1:8000`（X9）。**这是 recruit 数据完全进不了 X9 的根因**：扩展原来把 ingest 全 POST 到 8002。已在**下载的真实 zip** 内核对 background.js 确为 8000（0 处 8002）。
- `~` Fixed: `routers/extension_ingest_compat.py` 的 douyin 路由 bug —— 原 `ingest_snapshot(..., platform="foreign_trade")`（平台名写错、未传部门）改为 `platform="douyin", department_code=_dept(payload)`。运行中服务实测：`/api/companies/ingest`→A/90、`/api/douyin/ingest`→platform=douyin 入库评论+联系方式。
- `#` Note: **逐页采集后端链路已 DB 级实证**：免登录 POST `/api/companies/ingest`（payload 含 department_code）→ 直查数据库确认落库为 `company_name=端到端唯一测试公司777, department_code=foreign_trade, tier=A, score=90`。compat 路由前缀 `/api`（非 `/api/local`），不受登录中间件拦截、设计即免登录。
- `#` Note: 测试方法坑（留痕）——curl 内联中文 `-d` 会被 Windows shell 破坏、报 "error parsing the body"；PowerShell 在服务重启窗口期偶发 401。**正确测法**：curl `--data-binary @file`（JSON 写文件）或 PowerShell UTF8 字节 + 服务完全就绪后再测。结论以 DB 直查为准。
- `#` Note: **仅"真机浏览器打开页面→content script 抓取→发往插件 background"这一段未测**（开发机无 Chrome）。从 background 往后（→X9→DB）已实证。
- `#` Note: **批量「开始采集」（关键词→自动翻页）真实评估**：依赖 CompanyLeads 的 native host（`com.companyleads.helper`，127.0.0.1:8765）+ 一套 **~4000 行 Python 爬虫栈**（`scraper/`：cdp_helper 1158、helper_server 488、zhaopin 867、qzrc 765、platform_contract 660）+ 依赖 **Playwright + PaddleOCR + pandas**，且耦合 CompanyLeads 自有后端(8002)的任务队列。**这不是"搬一个 helper 文件"，是搬一个重型子系统**，且本机无 Chrome/Playwright/OCR/登录态，**完全无法验证**。结论：批量需在真机单独安装该 Python 栈；是否整体移植进 X9 待用户确认（详见下方诚实现状）。
- `#` Note: 扩展 ID 问题：合并扩展 manifest **无 `key`**，unpacked 加载每台机 ID 随机，native host 的 `allowed_origins` 无法预先匹配——若要批量，需给 manifest 加固定 `key` 钉死 ID，再让 install 脚本按该 ID 注册。

## 诚实现状（插件采集，2026-05-31）

- `#` Note: **全流程未真机测试**——开发机无 Chrome、未登录目标站。已验证：zip/manifest/文件齐全/JS 语法/后端 curl/ingest 直调入库。**未验证**：装进 Chrome → 真实页面抓取 → 入库 这一整条。
- `#` Note: **批量采集 helper 缺失**——`recruit/sidepanel.js` 写死提示「运行 install_companyleads.ps1」，但该 ps1 **在源项目 CompanyLeads 里就不存在**（从未移植）。批量采集（`127.0.0.1:8765` native host + CDP 翻页）暂不可用、报错属预期。**逐页采集**（content script 抓当前页→`backend:ingestCompany`→后端）不依赖 helper。
- `#` Note: `Error 1033 Cloudflare Tunnel` = usx9.us（同事服务器）隧道断，与本地/本次改动无关；本地测试用 `localhost:8000`。
- `#` Note: 通俗操作见 `docs/插件使用说明-通俗版.md`。

## 批量采集 helper 移植（2026-06-01，含回退点）

- `+` Added: 回退点 `F:\Claude_Project\_X9_rollback\20260601_082920_before_helper\`（快照 foreign-trade-extension + backend extension.py/main.py + 一键 `RESTORE_回退.ps1`），可随时退回"未接 helper、逐页采集可用"状态。
- `~` Fixed: 侧边栏 `recruit/sidepanel.js` 连不上 helper 时的吓人报错（"请先运行 install_companyleads.ps1"）改为中性提示——逐页采集不经过 helper，连不上不是错误。
- `+` Added: 合并扩展 `manifest.json` 加固定 `key`（取自 CompanyLeads），扩展 ID 钉死为 `idahdepjhfmldleebihlbnkmfhjbjbde`（与 native host allowed_origins 一致；实测 key→ID 推导吻合）。
- `+` Added: helper 栈搬入 `desktop/foreign-trade-helper/`（scraper/ 6 个 py、native_host/、start_all.ps1、start_chrome_cdp.ps1、requirements.txt、run.py；与源 byte-identical，diff 验证）。
- `+` Added: 一键安装脚本 `desktop/foreign-trade-helper/install_ft_helper.ps1`（创建 venv + 装依赖 + `playwright install chromium` + 写 config[backendUrl=:8000, department=foreign_trade, mode=client] + 注册 native host 绑定固定 ID）。PowerShell 解析器验证无语法错误。
- `~` Fixed: compat 路由 `extension_ingest_compat.py` 的 `_dept` 末尾兜底改为 `foreign_trade`（原 fallback 到全局 cross_border）——批量 helper 服务端推送无 cookie/无 payload 部门，靠此确保归入外贸部。语法校验通过。
- `#` Note: 数据流（代码追踪）：扩展→native host→start_all(client 模式跳过旧 8002、导出 COMPANYLEADS_BACKEND_URL=:8000)→cdp_helper(:8765)→scraper push→`:8000/api/{companies,talents}/ingest`→compat(默认 foreign_trade)→入库。
- `#` Note: **未真机验证**（开发机无 Chrome/Playwright/登录态）——受控 Chrome 唤起、翻页抓取、端到端入库需真机实测。安装/使用/排查见 `docs/批量采集-安装说明.md`。逐页采集不受影响、已验证可用。
- `#` Note: 工具异常留痕——本轮 PowerShell/Read 对 `foreign-trade-helper` 内 CRLF 文件渲染出现截断与一次"输出混入描述文字"的假象；用 `diff`(byte-identical) + `awk` 确认文件未损坏，结论以确定性工具为准。

## 批量采集 401 — 仍在定位（2026-06-01，勿轻信前述结论）

- `#` Note: ⚠️ 我已两次对 401 下错根因（先"僵尸实例"、又"非僵尸是请求差异"、再"僵尸实例"），**全部不可靠**。当前确凿事实仅两条：① 同一运行实例上，我手动 `httpx.post(/api/companies/ingest, json=带department_code)` → 200 入库；② 爬虫 `platform_contract.push_one()` 发同一路由 → 401。差异必在 push_one 实际发出的 HTTP 请求与我手动请求之间，**尚未抓包级定位，不下结论**。
- `#` Note: 已知 `normalize_company_entry` 会丢弃 `department_code`（实测 normalized keys 无该字段），但这不解释中间件层 401（compat 前缀 `/api` 不被 `/api/local` 中间件拦）。需进一步抓 push_one 实际 URL/headers/method 逐字节对比手动请求。

## 批量采集真因定位（2026-06-01，对照实测）

- `#` Note: **爬虫能跑通**：有 playwright 的 Python 跑 `job_platform_scraper.py --platform 51job` → 受控 Chrome(9222) attach → 抓到 51job 真实公司数据（6-8 条/页）。合并未破坏爬虫功能。
- `#` Note: 真因①（解释"合并前能用、合并后问题多"）：**playwright 装在本机私有 `E:\MiniConda`**（chromium 在 `F:\python_envs\...`），合并环境/别人 clone 都没有 → "缺少 playwright" exit 1。结论：**必须靠 install 脚本每机现装**（方案一），复用本机环境无法让别人可用。
- `#` Note: 真因②：当时跑的是**旧 CompanyLeads helper**（root 指旧仓库、`PYTHON=sys.executable` 取无 playwright 的系统 python、推送旧 8002）。
- `#` Note: ⚠️ **自我纠错**——我曾写"401 是僵尸 uvicorn 实例所致"，**对照实测推翻**：同一清洁实例上，我手动用 httpx/urllib/curl POST `/api/companies/ingest` 全部 **200 并入库**（DB 实证 foreign_trade 共 15 条），**唯独爬虫 `platform_contract.py` 自己发的请求被 401**。差异不在服务端、不在实例数，而在**爬虫请求本身**（疑似带了 `X-CompanyLeads-Token` 头或其它触发中间件的因素）。真因③待定位（见下一步），但已锁定为"爬虫请求差异"，非服务端 bug。
- `#` Note: 教训重申：诊断必须基于对照实测，不可凭印象写结论（本条就是反例，已纠正）。

## 批量采集真机首测结果（2026-06-01）

- `#` Note: 用户真机首测：**helper 已连上**（"helper: 已连接，历史任务 1"），但采集**退出码 1 失败**。
- `#` Note: ⚠️ 自我纠错——我曾据"印象"在文档写"受控 Chrome 没起来/webSocketDebuggerUrl 为空"，**实测推翻**：`curl :9222/json/version` 返回有效 webSocketDebuggerUrl、`:8765/health` 正常、`:8002/api/stats` 返回 total=245。即**环境都正常**，exit 1 是**爬虫抓取目标站本身失败**（反爬/改版/未登录），非环境问题。已改正 `docs/批量采集-安装说明.md` 与本条。教训：诊断必须基于实测端口探测，不可凭印象写进文档。
- `#` Note: 当前跑的是**旧 CompanyLeads helper**（root=F:\Claude_Project\CompanyLeads），数据推旧后端 8002、**未进 X9**。须先用新 `install_ft_helper.ps1` 重装，root 才指向 foreign-trade-helper、推送才进 X9:8000。
- `#` Note: 结论：批量=真实爬虫，受目标站反爬/登录影响，**天生无法"直接用"**；要稳定采集走逐页。退出码 1 的具体平台原因需读任务日志（智联/人才端多为未登录）。AI 无浏览器，无法代验抓取。

## 验证规约（所有会话必须遵守）

- `#` Rule: **我编辑的源码目录 ≠ 用户实际拿到的产物。只看源文件不算验证完成。**
  - **插件（chrome 扩展）类改动**：必须以对应部门账号实际 `GET /api/local/extension/download` **下载真实 zip → 解包 → 核对内容**（manifest 引用的每个文件存在、importScripts/side_panel 路径正确、改动确已进入下发包），并 `node --check` 关键 JS，才算完成。
  - **前端页面改动**：必须 `build` 后再跑**部署脚本**（web: `build:root`+`deploy:root`；web-user: `build:deploy`+`deploy`）到 `desktop/backend/ui/{admin,portal}`，并确认部署 bundle 内容正确，才算完成——光 `npm run build` 页面不会变。
  - **后端改动**：以运行中的服务实测端点（登录态 + 实际 HTTP 码/返回），不靠"导入成功"或源码推断。
  - 详见桌面问题留痕 `C:\Users\Administrator\Desktop\工作留痕\外贸部改造-问题留痕记录.md`。

## 修复 — 合并插件 background 加载失败（importScripts 裸路径）

- `~` Fixed: `desktop/foreign-trade-extension/ft_background.js` 原 `importScripts("social/x9_sw.js")`，而该 wrapper 内部用裸文件名（`importScripts("xhs_runner.js")` 等）。MV3 中 importScripts 相对 service worker 所在的**扩展根目录**解析，裸名找不到 `social/` 下文件 → `social background failed to load (DOMException)`。改为根相对路径直接加载叶子文件（`social/x9_relay.js`、`social/xhs_runner.js`、`social/douyin_runner.js` + `recruit/background.js`），各自独立 try/catch。
- `#` Note: 以 ftuser 下载真实 zip 解包核对：ft_background 的 importScripts 目标全部存在于包内、node 语法通过、28 文件齐全。

## 修复 — 合并插件 manifest 侧边栏路径写错

- `~` Fixed: 重写 manifest 时把 `side_panel.default_path` 误写为不存在的 `ft_sidepanel.html`，导致 Chrome 报 "Side panel file path must exist / Could not load manifest"。改回 `sidepanel.html`，并逐项核对 manifest 引用的全部 17 处文件均存在。

## 修复 — 外贸门户采集页"加载失败" + 插件 nativeMessaging 权限

- `~` Fixed: `web-user/src/api/foreignTrade.ts` 路径双前缀 bug —— 门户 client 已自带 `API_BASE='/api/local'`，hook 里又写 `/api/local/foreign-trade/...` → 请求 `/api/local/api/local/...` → 404 →「加载失败」。改为 `/foreign-trade/dashboard`、`/foreign-trade/collection`，重建部署门户，bundle 无双前缀。（admin `web/` client base 为空串、写全路径，无此问题。）
- `~` Fixed: `desktop/foreign-trade-extension/manifest.json` 补回合并时遗漏的 `debugger`、`nativeMessaging` 权限。
- `#` Note: 侧边栏「helper 未安装」属预期——招聘批量采集依赖本地 helper（CDP 驱动翻页）；逐页采集无需 helper。

## Phase 4 — 插件合并 + 下载按部门路由

- `+` Added: 合并扩展 `desktop/foreign-trade-extension/`（MV3）—— `recruit/`（job_collector / zhaopin_click_bridge / qzrc_collector / background / sidepanel）+ `social/`（xhs/douyin content+runner+panel、x9_relay、x9_sw、x9_actor_config、popup）+ 根 `manifest.json`、`ft_actor.js`（下载时注入 department_code/actor）、`ft_api_config.js`（API base 指向 :8000 + fetch 包装给 ingest 注入 department_code）、`ft_background.js`（合并 SW）、`sidepanel.html`/`popup.html`。
- `~` Modified: `routers/extension.py` 的 `/api/local/extension/download` 按 `department_code` 路由 —— foreign_trade → 合并扩展 zip（个性化 ft_actor.js）；其余 → 原 TikTok zip（不变）。
- `+` Added: `routers/extension_ingest_compat.py` —— `POST /api/{companies,talents,xhs,douyin}/ingest` 转发 X9 ingest 服务（免登录，department 取 payload→session→默认），已在 main.py 注册。
- `#` Note: 以两部门账号实测下载得到两个不同且正确的 zip（外贸 28 文件含招聘+小红书+抖音、ft_actor 个性化 foreign_trade）；compat ingest 实测成功（company→A/90、xhs→评论+联系方式入库）。受限于无浏览器，未做真机 chrome 加载验证。

## Phase 3 — 小红书/抖音端到端（入库+清洗+联系方式+GPT判定）

- `+` Added: `desktop/backend/utils/xhs_cleaning.py`（contact 正则 EMAIL/PHONE/WECHAT/URL 移植自 XHS cleaning.py，`clean_text`/`parse_count_text`/`normalize_url`/`extract_contacts`）。
- `+` Added: `desktop/backend/services/xhs_lead_service.py` —— `ingest_snapshot`（兼容 XHS `notes` 与 Douyin `posts`，upsert 用户/笔记/评论、从评论文本+简介提取联系方式、写 collection_run/raw_snapshot、部门作用域、幂等去重）；`judge_users_with_gpt`（prompt_version `xhs-b2b-us-dropship-fit-v5`，输出 fit_score/fit_level/decision/intent_type，无 `OPENAI_API_KEY` 时安全跳过）。
- `+` Added: `desktop/backend/routers/xhs_leads.py` —— `POST /api/local/xhs/ingest`、`POST /api/local/xhs/douyin/ingest`、`POST /api/local/xhs/judge`、`GET /api/local/xhs/users`；已注册。
- `+` Added: 前端「社媒线索」页 `web/src/pages/department/SocialLeads.tsx` + `web/src/api/foreignTrade.ts` 的 `useXhsUsers`。
- `#` Note: 端到端验证 —— XHS+Douyin 快照入库，微信/邮箱从评论文本提取，看板 social_leads/contacts、平台分布含小红书+抖音、社媒采集面板联动；幂等重复入库不增用户。GPT 判定需 `OPENAI_API_KEY`。

## Phase 2-E — 招聘爬虫移植 + 接 X9 ingest

- `+` Added: 招聘爬虫移植到 `scrapers/recruitment/` —— `job_platform_scraper.py`（51job/智联·公司+人才）、`qzrc_scraper.py`（大泉州·公司+人才）、`platform_contract.py`（推送接口）、`README.md`。
- `~` Modified: `platform_contract.py` 推送目标改为 X9 `/api/local/{company-leads,talents}/ingest`（env `X9_INGEST_BASE` 默认 :8000）；会话登录（`X9_INGEST_USERNAME`/`X9_INGEST_PASSWORD`，外贸部账号 → 线索 department_code=foreign_trade），登录一次复用 cookie。
- `#` Note: 端到端验证 —— testadmin2 登录推送，公司/人才各 1 条成功入库（新公司 A 级）。实际抓取需在装 Playwright、已登录目标站的机器上运行。

## Phase 2 — 招聘端到端（入库+评分+管理页）

- `+` Added: 评分/排除/LLM 模块移植自 CompanyLeads —— `desktop/backend/utils/{job_keyword_rules,job_llm_scorer,job_exclusion}.py`（排除预设 JSON 改存 X9 `DATA_DIR`）。
- `+` Added: `desktop/backend/services/company_lead_service.py`（`ingest_company`/`ingest_talent`，部门作用域，关键词+LLM 合并评分；未配置 `LLM_*` 时降级关键词评分）。
- `+` Added: `desktop/backend/routers/company_leads.py` —— ingest/list/patch（公司 + 人才）；已注册。
- `+` Added: 前端 `web/src/pages/department/{CompanyLeads,TalentLeads}.tsx` 管理页接真实列表 + `useCompanyLeads`/`useTalentLeads`。
- `#` Note: 验证 —— 入库 4 公司+2 人才，评分 A/A/B/未评级（工厂正确降权）、合作类型分类、排除词命中、看板/采集面板联动。排除词沿用 CompanyLeads 原配置（含 "tiktok shop" 官方平台），可在 `DATA_DIR/exclusion_presets.json` 调整。

## 决策：TikTok 不删除 + 本地空库归因

- `#` Note: 用户决策 —— TikTok 板块**不删除**（"根本不要删，就是不同的入口"）。**取消原 Phase 5（物理清理 TikTok）**；TikTok 永久作跨境部入口，外贸部按 `department_code` 走另一套入口。
- `#` Note: 本地库为空非数据丢失 —— DB 被 `.gitignore` 忽略（`desktop/data/creators.sqlite`、`*.db`），fresh 克隆只有代码、`init_db()` 仅种 superadmin；真实数据在 usx9.us 生产库。本次后端改动仅新增、无删除/DROP/迁移。

## 部署拓扑澄清 + 本地测试账号

- `#` Note: 本机 `X9_AI_system_fresh`（空 SQLite）与 usx9.us **不是同一套**；usx9.us 由**同事电脑作服务器**伺服。上线流程：`git push` → 同事服务器拉取部署。开发用 `_fresh`，本地验证用 `localhost:8000`。
- `+` Added: 本机种入测试账号（密码 `<password redacted>`）：`superadmin`、`testadmin1`(cross_border)、`testadmin2`(foreign_trade)、`testuser`(cross_border)、`ftuser`(foreign_trade department_user)。

## Phase 1 修正 — 界面按部门区分（关键架构修正）

- `#` Note: 同一套部署同时服务跨境部(cross_border)与外贸部(foreign_trade)；前端原仅按角色选菜单（全局）。改为**按 `department_code` 条件渲染**：跨境部保持原 TikTok 界面，外贸部显示招聘+社媒界面。
- `~` Modified: 恢复跨境部原界面（web/web-user 的 menus/Dashboard/Business/Collection/CollectImport/routes/App）至 TikTok 版本。
- `+` Added: 外贸界面独立文件（`ForeignTradeDashboard/ForeignTradeBusiness/ForeignTradeCollection/ForeignTradeImport` + `CollectJobs/CollectSocial`）；`Sidebar`/路由按 `department_code === 'foreign_trade'` 切换（web 用 `useRoleStore().currentUser`，web-user 用 `useMe().user`）。

## Phase 1 — 看板与采集面板先行（数据地基 + 外贸口径聚合）

- `+` Added: 招聘模型 `models/{company_lead,talent_lead}.py`、社媒模型 `models/social_lead.py`（7 张 `xhs_*` 表），均含 `department_code`；在 `models/__init__.py` 注册（X9 用 `create_all` 自建表，无 Alembic）。
- `+` Added: 外贸口径聚合路由 `routers/foreign_trade.py` —— `GET /api/local/foreign-trade/dashboard`、`/collection`；部门作用域，空表返回真实 0。
- `~` Modified: 两套前端菜单/看板/采集面板改为外贸 IA（招聘网站/小红书抖音/表格导入 + 公司客户线索/跨境人才库/社媒线索/线索推荐）。
- `#` Note: 方向决策 —— 完全原生集成（并入 x9db）、第一阶段交付看板与采集面板。
- `#` Note: 部署机制 —— desktop 从 `ui/admin`（管理端）与 `ui/portal`（门户）伺服前端。更新页面须 `build:root/deploy:root`、`build:deploy/deploy`，再浏览器硬刷新（FileResponse 实时读盘，无需重启）。
