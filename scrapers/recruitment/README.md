# 招聘网站爬虫（外贸部 · Phase 2-E）

从 51job / 智联 / 大泉州人才网抓取**跨境公司客户**与**跨境人才**线索，推送到 X9 后端自动评分入库。
移植自 CompanyLeads，`platform_contract.py` 已改为推送到 X9 的 `/api/local/{company-leads,talents}/ingest`。

## 一次性准备

```powershell
pip install playwright httpx
python -m playwright install chromium
```

## 环境变量（推送目标 + 鉴权）

| 变量 | 说明 | 示例 |
|------|------|------|
| `X9_INGEST_BASE` | X9 desktop 后端地址 | `http://127.0.0.1:8000` |
| `X9_INGEST_USERNAME` | **外贸部**账号（决定线索 department_code=foreign_trade） | `<外贸部账号>` |
| `X9_INGEST_PASSWORD` | 该账号密码 | `<该账号密码>` |
| `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` | 可选，配置后启用 LLM 评分 | — |

> 入库接口需登录态，脚本会用上面账号登录一次、复用会话 cookie。

## 运行（PowerShell，先设环境变量再跑）

```powershell
$env:X9_INGEST_BASE="http://127.0.0.1:8000"
$env:X9_INGEST_USERNAME="<外贸部账号>"; $env:X9_INGEST_PASSWORD="<该账号密码>"
cd f:\Claude_Project\X9_AI_system_fresh\scrapers\recruitment

# 51job 公司客户（公开信息，登录可选）
python job_platform_scraper.py --platform 51job --max-pages 20

# 智联 公司客户（需在弹出的浏览器里登录智联）
python job_platform_scraper.py --platform zhaopin --keywords "跨境销售,亚马逊运营"

# 智联 跨境人才（需登录企业端）
python job_platform_scraper.py --platform zhaopin_resume --keywords "跨境运营,亚马逊"

# 大泉州 公司客户（--enrich 补简介/地址）
python qzrc_scraper.py --mode job --max-pages 5 --enrich

# 大泉州 跨境人才
python qzrc_scraper.py --mode resume --max-pages 10

# 预检不入库（核对抓取质量）
python job_platform_scraper.py --platform 51job --max-pages 2 --dry-run
```

## 说明

- 公司类 → `company_leads`，人才类 → `talent_leads`；后端自动做关键词+LLM 评分、分级（A/B/C）、排除词过滤、去重。
- 反爬：脚本带随机延迟、验证码检测（检测到会暂停等人工通过），请勿并发暴力抓取。
- 排除词（含竞品/“tiktok shop”官方平台/无关行业/自有公司）可在 `DATA_DIR/exclusion_presets.json` 调整。
- 浏览器扩展驱动（侧边栏一键采集）属 Phase 4，本目录是 CLI 方式。
