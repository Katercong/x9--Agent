# X9 Database — API & Schema Changelog

廖 那边写代码前 / 改代码前先扫一眼这里。约定：

- `+` 加字段/表/接口/查询：**永不破坏**，廖那边代码继续跑，看到新东西想用就用
- `~` 修改：**有可能影响**，需要协调
- `-` 删除/重命名：**会破坏**，张这边删/改之前必须先在 CHANGELOG 公告 + 通知廖

格式：日期 / 改动类型 / 描述。

廖那边可以 `GET /api/v1/version` 拿到本文件最后修改时间，发现变了就过来扫一眼。

---

## 2026-05-09 — v3.11.0（迁移至 192.168.1.171 共享服务器）

- ~ 部署位置：`F:\Claude_Project\Database\`（张本机）→ `\\192.168.1.171\FShare\Database\`（共享服务器，常开机）
- ~ 实习生素材：`F:\实习生\` → `\\192.168.1.171\FShare\实习生\`
- ~ 访问入口：`http://192.168.1.168:18765/` → `http://192.168.1.171:18765/`
- + `migrate_to_171.bat` — 一键推代码 + db + 实习生素材到共享盘
- + `setup_on_171.bat` — 在 171 上首次部署（venv + deps + migrations）
- + `run_on_171.bat` — 171 上启动服务（用 venv，监听 0.0.0.0:18765）
- 注：代码里 `F:\实习生\...` 路径字符串无需改 — 在 171 上 `F:\` 即共享盘根
- 注：SQLite 始终被 171 本地进程独占访问（不走 SMB），避免锁损坏

## 2026-05-09 — v3.10.0（钉钉 webhook：schema 变更实时广播）

廖关心数据库结构改动，每次靠 CHANGELOG 被动扫不够及时。这版加上**事件订阅 + 钉钉机器人推送**。

- `+` migrate_v15：`webhook_subscriber` 表 + 注册成 generic CRUD resource (`/api/v1/data/webhooks`)
  - 字段：name / kind (`dingtalk` | `http`) / url / secret (加签密钥) / keyword (关键词模式) / events (JSON 数组, null=全收) / active / last_fired_at / last_status / last_error
- `+` `app/notifier.py`：
  - `emit(event, summary, details=, actor=, full_dump=)` 异步线程发送，不阻塞调用方
  - 钉钉 markdown 消息体 + 加签模式自动生成 timestamp+sign
  - 关键词模式：自动确保关键词出现在 title 里
  - `build_schema_dump_markdown()` 输出全库 schema dump (35 张表 + 13 命名查询, ~22KB)
- `+` 4 个 schema 变更端点（v1.py）每个成功后 emit 事件：
  - `schema.create_table` (大变动 → 附 dump 链接)
  - `schema.add_column`
  - `schema.drop_column`
  - `schema.drop_table` (大变动 → 附 dump 链接)
- `+` `GET /api/v1/schema/dump?format=markdown|json` — 完整 schema 导出，钉钉消息里点链接打开就是这个
- `+` `POST /api/v1/webhooks/{id}/test` — admin 一键发条测试消息验证配置
- `+` 前端 设置页"📢 钉钉通知"卡片：列出订阅者 / 测试 / 启停 / 删除 / 添加（输入 name + URL + 关键词 X9，1 行搞定）

### 廖配置流程（钉钉端，2 分钟）

1. 钉钉群 → 群设置 → 智能助手 → 添加机器人 → 自定义
2. 安全设置：勾"自定义关键词"，填 `X9`（推荐，比加签简单）
3. 复制 webhook URL（形如 `https://oapi.dingtalk.com/robot/send?access_token=xxxxx`）
4. X9 数据库前端 → 设置 → "📢 钉钉通知" → 填 name=`liao_dingtalk` + URL + 关键词 `X9` → 添加
5. 点 "📨 测试" 按钮 → 几秒后钉钉群里能看到测试消息
6. 完成后任何 schema 改动都会自动推到群

### 验证

| 测试 | 结果 |
|---|---|
| 订阅者列表 / events filter | ✓（events=null 时全收） |
| markdown 格式渲染 | ✓ 含事件名、摘要、操作人、时间、details 列表 |
| 关键词自动注入 title | ✓ |
| 加签 HMAC-SHA256 timestamp + sign | ✓ |
| schema dump (35 表 + 命名查询) | ✓ 22KB markdown |
| 异步线程不阻塞 | ✓（fire-and-forget） |

## 2026-05-09 — v3.9.1（话术生成器升级：智能产品推荐 + 自动渠道 + fit-level 调调）

基于 v3.9.0 把廖字段并入 creator 主表后，话术生成器从"被动接收信号"升级为"主动用信号决策"。

- `+` `POST /api/v1/ai/outreach/suggest_products` — 新端点
  - 输入：`{creator_id, limit?}`
  - 按 `recommended_product_type` → `*_fit` 分数最高 → `primary_product_category` → `category_tags` 四级回退选品类
  - 返回：top N 产品（按 is_main_push DESC, id ASC）+ 建议渠道 + fit_signals（fit_level / priority_score / review_required / risk_summary / fit_scores）
- `~` `POST /api/v1/ai/generate_outreach` 三处升级:
  - `channel: "auto"` 新增（默认）— 有邮箱用 email，否则 tiktok_dm
  - `product_ids` 现在可省略 — 后端自动按 fit 推荐 top 3
  - 响应新增字段：`auto_picked_channel / auto_selected_products / fit_signals`
- `~` `build_prompt` system 段新增"Tone calibration based on creator fit signals"小节：
  - A/S 或 priority_score≥60 → 暖一点 + 长期合作语气
  - B 或 priority_score≥40 → 标准专业语气
  - C/D 或 priority_score<40 → 短而克制，不许诺长期合作
  - `review_required=1` → 用 'we'd love to explore' 而非 'we'll send you'
  - `risk_summary` 进 prompt（仅供 LLM 调调，不让它告诉创作者）
- `~` 前端 "📝 生成邀约话术" 弹窗:
  - 渠道下拉默认"🤖 自动"
  - 新增"🤖 智能推荐"按钮 — 一键预填产品 + 渠道 + 显示 fit_signals
  - 不勾产品也能点"📝 生成"（后端补刀）
  - 结果区显示 🎯 fit 徽章 + 🤖 自动选了什么的提示

### 验证（直接调用辅助函数）

| 创作者 | fit_level | priority_score | 自动渠道 | 推荐产品 | 调调提示 |
|---|---|---|---|---|---|
| #1 cicigiginana | D | 18 | tiktok_dm | 3×女护 | LOWER-FIT 短克制 + missing_contact 风险 |
| #110 (B 档高分) | B | 66 | email | 3×女护 | HIGH-FIT 暖语气 + 长期合作 |
| #106 (有邮箱) | — | — | email | — | — |

## 2026-05-09 — v3.9.0（creator 主表合并廖 lead 池字段 + 话术生成器接信号）

- `+` migrate_v14：`creator` 新增 50 列（廖独有的评分/推荐/证据字段），ALTER ADD 全 NULL 友好
  - 优先级：`priority_score / fit_level / priority_level / queue_type / outreach_priority`
  - 品类拟合：`primary_product_category / primary_product_fit_score / feminine_care_fit / pet_care_fit / home_care_fit / adult_care_fit / mom_baby_fit / health_mask_fit`
  - 质量子分：`data_quality_score / contactability_score / content_format_score / commercial_value_score / follower_scale_score / audience_fit_score`
  - 推荐：`recommendation_status / recommended_product_type / recommended_collab_type / recommendation_score / recommendation_reason / risk_summary / next_action / review_required / review_status`
  - 证据：`fit_evidence_source_json / matched_keywords_json / evidence_strength / evidence_text_json / risk_tags_json / positive_tags_json / content_format_status`
  - 元数据：`bio / has_email / external_links_json / source_video_url / source_video_title / source_video_description / search_keyword / collected_at / last_seen_at`
  - 版本戳：`score_version / tag_version / rec_version / scored_at / tagged_at / recommended_at`
- `+` ETL：`tk_creators` → `creator` 一次性 UPSERT，匹配键 `(platform, lower(handle))`
  - 64 行重叠：廖字段非空时覆盖 creator，BD 字段（owner_bd / current_status / first/last_contact_date / store_assigned / notes）保留不动
  - 66 行 lead 独有：INSERT 进 creator（current_status='prospect', source='scraper_liao'）
  - creator 行数 66 → 132，outreach 101 行 FK 全部完整保留
- `+` `tk_creators` 表保留作为廖爬虫的原始落地表（每天可继续 UPSERT，不会被覆盖）
- `~` `app/outreach_ai.py` build_prompt：新增 8 个信号字段进 user_parts
  - `primary_product_category / fit_level + priority_score / recommended_product_type / recommended_collab_type`
  - `evidence_text_json` 抽取 5 条最相关 snippet（feminine_strong / pet_care / commerce_signal 等）
  - `risk_summary / recommendation_reason` 作为 AI 上下文提示
  - 实测 input token 从 ~750 涨到 ~950，证明 prompt 携带

### 廖那边要知道的

- 你继续往 `tk_creators` 写数据，**不会**自动同步到 `creator`。需要再次合并时跑 `python scripts/migrate_v14.py`（idempotent）
- `creator` 表上现在能直接读到你写的 priority_score / fit_level / evidence_text_json 等字段
- 如果你要给 lead 池字段加新列：直接对 `tk_creators` ALTER ADD（你有 admin 权限），下次 ETL 时把列名加进 migrate_v14 的 NEW_COLS 即可

## 2026-05-08 深夜 — v3.8.2（DROP 端点 + key scope 分级 + lead 池规整）

按廖需求单 P3 #9（key scope）+ #10（DROP 端点）完成；前端 Lead 池切到 tk_creators。

- `+` `DELETE /api/v1/tables/{name}?confirm=true` — drop dynamic table（拒绝内置）
- `+` `DELETE /api/v1/tables/{name}/columns/{col}?confirm=true` — drop column（依赖 SQLite 3.35+，本机 3.43）
  - 拒绝条件：col 在 upsert_keys / json_cols / fk_lookup / 是 PK
- `+` `api_key.scopes` 列（migrate_v13）— JSON 数组，NULL = 走老 role 三档
  - scope 语法：`'admin'` / `'admin:<pat>'` / `'write:<pat>'` / `'read:<pat>'`，pattern 用 fnmatch
  - 写权限语义：`admin > write > read`；admin 隐含 write+read，write 隐含 read
  - 例：`['write:tk_*']` = 只能 bulk/patch tk_* 资源；`['admin:tk_*', 'read:*']` = tk_* 全权 + 全部读
- `+` `PATCH /api/v1/auth/keys/{key_id}/scopes` — admin 给 key 设 scopes（body: `{"scopes": [...]}` 或 `null`）
- `~` 写端点（bulk/patch/delete/create_table/add_column/drop_table/drop_column）增加 `assert_can(user, action, resource)` resource 级 scope 检查
- `~` 前端 "🕷️ Lead 池" tab → `/api/v1/data/tk_creators`（之前指 creator_leads，廖另建了 tk_creators，130 行）
- `-` migrate_v11 撤出 `creators` 表 + `creator_leads` slug（migrate_v12 清理）；廖在用 `tk_creators`
- `-` 删 3 条 demo lead 数据（id=demo_001..003）

向后兼容：所有现有 key（无 scopes）行为零变化，仍走 role 检查。

## 2026-05-08 晚 — v3.8.1（高级查询语法 + 清理 probe 脏数据）

按廖需求单 P0+P1 实现：

- `+` `?col__gte` / `__lte` / `__gt` / `__lt` 区间过滤
- `+` `?col__in=a,b,c` IN 列表（也支持重复 `?col=a&col=b`）
- `+` `?col__like=%text%` 透传 LIKE / `?col__icontains=text` 大小写不敏感包含
- `+` `?col__isnull=true|false` NULL / NOT NULL 过滤
- `+` `?order_by=col1:desc,col2:asc` 多键排序（旧 `?order_by=col&desc=true` 仍兼容）
- `~` 清理 `creator` 表的 `probe_x_a/b_*` 测试列 + `liao_keytest_*` 测试表
- `~` 廖文档加 v3.8.1 节 + P3 #8 误会澄清（unlock 是 D-015 决策不是 bug）

## 2026-05-08 — v3.8.0 (廖爬虫 lead 池接收层 + 内置表加列开放给 admin)

- `+` **9 张新表（廖端数据接收层）**，并行加表零破坏 — 不动现有 `creator` / `outreach` 主表：
  - `creators` — 爬虫 lead 池，VARCHAR(120) id，含 priority/fit/scoring 等 60+ 字段
    - **URL slug 是 `creator_leads` 不是 `creators`**（避让 X9 主表 `/api/v1/data/creators`）
    - 廖灌数据：`POST /api/v1/data/creator_leads/bulk`，upsert by `(platform, handle)`
  - `raw_observations` — 每次抓取的原始 JSON 留底，upsert by `content_hash`
  - `tag_definitions` — 标签字典，已 seed **79 个**：8 risk + 23 positive + 7 product_category + 7 product_fit + 12 content_vertical + 10 content_format + 12 collaboration
  - `creator_tags` — creator × tag 多对多，upsert by `(creator_id, tag_code)`
  - `creator_recommendations` — AI 推荐结果（按 rec_version 多版本）
  - `review_tasks` — 人工审核队列
  - `system_logs` — 廖端日志 append-only
  - `extension_sessions` / `extension_commands` / `extension_run_progress` — Chrome 扩展协调（心跳 / 命令队列 / 运行进度）
- `+` `scripts/migrate_v11.py` 幂等运行（自动检测旧版 `creators` stub 并安全重建）
- `+` 80+ 索引覆盖核心查询路径
- `~` **内置表加列开放给 admin** — `POST /api/v1/tables/{name}/columns` 不再卡 `is_dynamic`，张和廖都能给 `creator` / `outreach` / `product` 等内置表加新字段。仍走 `require_admin`，readonly/user 角色被拒
- 后续 ETL：lead 池 `creators` → 主表 `creator` 由专门脚本做（待建）
- `+` **前端新 tab "🕷️ Lead 池"**（view-leads）— 张和廖在浏览器里直接看 lead 池：
  - 筛选：平台 / fit_level (S/A/B/C) / 主品类 / 是否有邮箱 / 关键词搜索
  - 列：handle / 名称 / 粉丝（M/K 缩写）/ Fit 徽章 / Priority / 主品类 / 邮箱 / 状态 / 采集时间
  - 空状态提示："廖爬虫开始灌数据后这里会自动显示"
  - 默认按 priority_score 降序
- `+` 3 条 demo lead 数据（id=demo_001..003）让张能立刻看到 UI 效果，可手动 DELETE

## 2026-05-07 — v3.7.1 (会话交接包 + 修复 #nav:changelog 等无效 nav)

- `+` `docs/项目交接.md` — 新会话第一份必读
- `+` `docs/决策日志.md` — 13 条架构决策 + 替代方案为何被否决
- `+` `docs/进行中任务.md` — 当前 WIP + 后续 backlog（按需求确认表逐条对照）
- `+` `docs/术语表.md` — 项目自定义名词 / 业务术语 / 技术约定
- `+` `docs/文件地图.md` — 代码入口 + 各文件一句话描述
- `+` `docs/会话恢复指令.md` — 6 套 kickoff prompt（通用 / WIP 接续 / 排错 / 加新功能 / 紧急 / 廖专用）
- `~` 升级 agent 加载列表：现在共 12 份文档作为系统提示知识库（之前 6 份）
- `~` 修复 agent 生成 `#nav:changelog` 等无效 tab 跳转报错：
  - 收紧 agent 系统提示，明确 7 个有效 nav 目标
  - 前端 aiAction 加 fallback：识别不到的 nav 名自动映射到对应 docs 文件（changelog → /docs/CHANGELOG.md）

## 2026-05-07 — v3.7.0 (实时热搜抓取 + AI 分析 — 任务 2.2.2 升级)

### 数据层（migrate_v10）

- `+` `keyword_snapshot` 表 — 每次 `tk_hot_keyword` 被 INSERT 或 UPDATE 自动写一行
  - 给前端做趋势曲线 / 异动检测 / 历史对比
  - 由 SQLite trigger 自动触发，**廖那边只管 upsert，不用关心 snapshot**
- `+` `scrape_run` 表 — 每次抓取任务的元数据（开始/结束时间 + 来源 + 新增/更新/失败统计）
- `+` 3 个 trigger：
  - `trg_kw_snapshot_insert` — INSERT 时写 snapshot
  - `trg_kw_snapshot_update` — 关键指标变化时写 snapshot
  - `trg_kw_auto_category` — 关键词文本启发式自动归类（pad → female_care / puppy → pet / newborn → baby / underpad → home_care / mask → mask）

### AI 分析层（app/keyword_ai.py）

- `+` `POST /api/v1/ai/keywords/enrich` — 批量给关键词自动：
  - 分类（必填，7 选 1）
  - X9 相关性评分 0-1（< 0.2 自动停用）
  - 是否疑似竞品词
  - 一句话理由
  - 用 `title_optimizer` feature 绑定的 LLM
- `+` `GET /api/v1/keywords/dashboard` — 实时仪表盘数据：
  - 总体统计 / 类目分布 / 增长率 Top / 搜索量 Top / 7 天历史 / 最近 5 次抓取走计
  - 无需认证（只读）
- `+` `GET /api/v1/keywords/{id}/trend` — 单个关键词的历史快照（折线图用）

### 抓取调度模板（scripts/scrape_tk_hot.py）

- `+` 廖可以直接复制这个模板改 `fetch_keywords_real()` 即可：
  - 内置示例：随机扰动的演示数据 (`fetch_keywords_demo`)
  - 自动创建 `scrape_run` 记录 + 走计统计
  - 调 `/api/v1/data/tk_hot_keywords/bulk` upsert，自动触发 snapshot 写入
  - 命令行：`python scripts/scrape_tk_hot.py --source demo --n 12`
  - 真实抓取建议：Playwright 模拟 / Pentos+TikBuddy 第三方 API / TT 公开 hashtag 页
- 调度建议：
  - Linux/Mac：crontab `*/30 * * * *`
  - Windows：任务计划程序 30 分钟触发器

### 前台 — 新 "🔥 TK 热搜" tab

- `+` 实时仪表盘（**30 秒自动轮询**）：
  - 顶栏：上次抓取时间 / 来源 / 新增更新数
  - "📊 总体" + "📁 类目分布" 两张卡（带横向 bar）
  - "🚀 增长率 Top 8" + "📈 搜索量 Top 8" 两张表（点击关键词看趋势曲线）
  - "🕘 最近抓取走计" 折叠区
- `+` 操作按钮：
  - 🔄 立即刷新（手动拉一次仪表盘）
  - ▶ 立即抓取（前台直接触发 demo 抓取，方便测试，不用开 cmd）
  - 🤖 AI 分析未分类（一键调 enrich，处理最多 50 条 category_hint=NULL 的）
- `+` 关键词点击 → 弹窗 SVG 折线图（基于 keyword_snapshot 历史）

### 验证结果

| 测试 | 结果 |
|---|---|
| dashboard 返回正确字段 | ✓ (totals/by_category/rising/volume/history/recent_runs) |
| INSERT trigger 写 snapshot | ✓ (24→25, 自动 +1) |
| UPDATE trigger 写 snapshot | ✓ (vol 变化触发，2 条历史可查) |
| 启发式自动分类（修复 BEFORE INSERT bug 后）| ✓ pad→female_care / puppy→pet / newborn→baby / 无关键词→NULL |
| scrape_tk_hot.py CLI demo 模式 | ✓ run_id=1, added=4 updated=2 |
| scrape_run 走计写入 + dashboard 显示 | ✓ |
| 单关键词 trend 端点 | ✓ 返回 SVG 用的快照序列 |

## 2026-05-07 — v3.6.0 (任务 2.2.2 + Doc Viewer 修复)

### 任务 2.2.2 — TK 热搜关键词标题优化器

- `+` migrate_v9：`tk_hot_keyword` 表（关键词 + 搜索量 + 增长率 + 排名 + 区域 + 品类提示 + 原始 metrics + 证据样本）
- `+` 注册为通用 CRUD resource（`tk_hot_keywords`），upsert key `(keyword, source_platform, region)` —— 廖那边 `POST /api/v1/data/tk_hot_keywords/bulk` 直接灌
- `+` 24 条 bootstrap seed（女护 6 / 宠物 6 / 母婴 4 / 成人 4 / 家居 4），`notes='bootstrap_seed - replace with scraper data'` 标识
- `+` `llm_feature.title_optimizer` 行（可独立绑模型，不影响其他 AI 功能）
- `+` 3 条命名查询：
  - `hot_keywords_recent` — 近 N 天热搜，按搜索量降序
  - `hot_keywords_by_category` — 按品类筛 + 加权排序（vol × (1+growth)）
  - `hot_keywords_growing` — 增长率最快（趋势追踪）
- `+` `app/title_optimizer.py`：核心模块
  - `POST /api/v1/ai/optimize_title` — 6 段 prompt + JSON 输出，自动按品类配关键词
  - `GET /api/v1/ai/title/info` — 检测就绪 + 数据新鲜度 + bootstrap 警告
- `+` 4 个目标平台限制：TikTok 100/Temu 80/eBay 80/独立站 100，自动 char-count + 超限标红
- `+` 复用 `outreach.banned_phrases` 做合规检查，标题里命中"FDA-approved"等会闪红
- `+` 前台 产品编辑窗顶部"🔍 用 TK 热搜优化标题"按钮：
  - 弹窗选目标平台 / 区域 / 候选数量 / 关键词来源（自动 / 手动勾选）
  - 结果卡片显示每条候选 + char 进度条（绿/橙/红）+ 主关键词 + 一句 rationale
  - "📋 复制" 按钮 + "✓ 用这条替换 name_en" 按钮（一键写回数据库 + 审计 log）

### Doc Viewer 修复（agent 链接 docx 失败的问题）

- `+` `/docs/{name}` 扩展支持 5 种格式：`.md / .docx / .pdf / .pptx / .xlsx`
- `+` 跨目录搜索：`docs/` + `F:\实习生\C达人建联\` + `F:\实习生\A社媒\`（白名单）
- `+` 各类型独立渲染：
  - `.docx` → python-docx 抽段落 + 标题 + 表格 → HTML
  - `.pptx` → python-pptx 抽每张 slide 文字 → HTML
  - `.xlsx` → openpyxl 渲染前 200 行 / sheet → HTML 表
  - `.pdf` → 直接以 application/pdf 服务（浏览器原生预览）
  - `.md` → 原有 markdown 渲染保留
- `+` 顶部"返回主界面"按钮 + 文件类型 badge + "下载原文件"链接
- `+` 安全：路径白名单 + 路径穿越拦截（`..` 立即 404）+ 扩展名白名单
- `+` `/docs/raw/{name}` 端点：强制下载原文件（非渲染）

### 验证结果

| 测试 | 结果 |
|---|---|
| Doc viewer .md / .docx / .pdf / .pptx / .xlsx | 5 种全 200 ✓ |
| Doc viewer 路径穿越 / 不存在文件 | 全部 404 ✓ |
| title/info 显示 24 条 seed + bootstrap warning | ✓ |
| 命名查询 hot_keywords_recent / by_category | 返回正确排序 ✓ |
| optimize_title for BU02P155 on tiktok | 3 候选全 ≤100 字符，含 "period underwear" 等真实关键词 ✓ |
| optimize_title for EU06FDXS on temu (80 字符限制) | 3 候选全 ≤80 字符 ✓ |
| readonly 角色调 optimize_title | 403 ✓ |

## 2026-05-07 — v3.5.0 (3.1.2 + 3.1.3 + 3.2.1 前端)

### 3.1.2 + 3.1.3 — 达人筛选与竞品排除

- `+` migrate_v8：creator 表增 4 列
  - `engagement_rate` REAL — 互动率 (0~1)
  - `last_post_at` TEXT — 最近发帖
  - `excluded` INTEGER (default 0) — 黑名单标记
  - `excluded_reason` TEXT — 排除原因
- `+` 新表 `competitor_brand` — 25 条预置（女护 10 / 母婴 7 / 宠物 5 / 成人 3）
- `+` 新表 `creator_competitor_collab` — 多对多 + 证据 URL + 置信度
- `+` 4 条命名查询：
  - `creators_mid_tier_koc` — 1K-50W 中腰部 KOC（默认排除 excluded + 竞品合作）
  - `creators_high_engagement` — ≥3% 互动率
  - `creators_blacklisted` — 已排除 / 已合作竞品的统一视图
  - `creators_by_content_match` — 按 category_tags 关键字匹配
- `+` 前台 达人 tab 高级筛选行：
  - 粉丝区间下拉（含"⭐ 中腰部 KOC 1K-50W"快捷项）
  - 最低互动率下拉（≥1% / 3% / 5% / 10%）
  - "排除竞品合作" 复选框（默认 ✓）
  - "排除黑名单" 复选框（默认 ✓）
  - "查看黑名单" / "⭐ 中腰部 KOC" 一键按钮（直接调命名查询）
  - 已排除达人在列表里灰显
- `+` 创作者详情页 3 个新操作：
  - "📝 生成邀约话术" — 选产品+渠道，弹窗显示生成结果，含合规标签 + token 用量 + 一键复制
  - "＋ 记录竞品合作" — 从 25 个预置竞品里选，加证据 URL 和置信度
  - "排除/恢复" — 切换 excluded 标记，必须填原因
- `+` 创作者详情页"⚠ 竞品合作记录"段落 — 已合作过的竞品列出 + 删除单条按钮

### 3.2.1 — 邀约话术生成器前端 UI

- `+` 创作者详情 → "📝 生成邀约话术" 按钮，连通 `POST /api/v1/ai/generate_outreach`
- `+` 生成弹窗：
  - 顶部显示 template_family / channel / language / Provider/model / token 用量
  - 合规检查：通过显示绿色 ✓，命中红色高亮 + 替换建议
  - 主体可编辑 textarea（生成内容可直接二次修改）
  - "📋 复制全文" / "标记已复制" / outbox_id 显示
- `~` `run.bat` 加 `migrate_v8.py` 调用

### 验证结果

| 测试 | 结果 |
|---|---|
| 6 个新 resource 注册 | ✓ |
| 25 条竞品种子 | ✓ |
| 中腰部 KOC 命名查询 | ✓（仅 1 条达人有 followers 数据，正确返回 la_patrona_diana） |
| 高互动率查询 | ✓（设 0.045/0.078 → 返回 2 个 ≥3%） |
| 黑名单视图 | ✓（同时返回 excluded=1 和 competitor_collabs 的达人） |
| 内容匹配查询 | ✓（关键字 "女性" 返回 3 条） |
| PATCH excluded round-trip | ✓ |

## 2026-05-07 — v3.4.0 (邀约话术生成器 3.2.1 一期)

- `+` migrate_v7：4 张新表
  - `app_config` — 系统级 KV 配置（outreach 政策 / 品牌信息 / 禁词清单）
  - `brand_profile` — 品牌资料抽取条目，可按 category_scope 分类
  - `outreach_example` — few-shot 历史话术库
  - `outbox` — 半自动触达队列（draft / ready / copied / sent / failed / archived 状态机）
  - 全部注册为通用 CRUD resource（在 `_meta_resource`）
- `+` 种入 v1 默认值（在 `app_config`）：佣金 20% / 1 包寄样 / 全 SKU 可寄 / 7 天物流 / X9 Team 签名 / x9x9.us 网站 / sales@sanitexindustries.com 邮箱
- `+` 11 项合规红线（`outreach.banned_phrases`）：FDA-approved / the safest / 100% leak-proof / treat / cure / prevent disease / guaranteed sales 等，配套 6 项替换建议
- `+` 4 条品牌资料种子（X9 定位中英 + pet/feminine 系列摘要）
- `+` `pet_care.tiktok_dm.base_v1` 固定话术（你给的那段，20% commission，X9 Team 签名）
- `+` `import_outreach_examples.py`：从 `跨境运营日SOP流程及目标.xlsx` 抽 28 条 BD 手写话术（覆盖 邀约 / 独立站 / 引流 三个 sheet）
- `+` `app/outreach_ai.py`：核心生成器 + outbox 写入
  - `POST /api/v1/ai/generate_outreach` — 6 段 prompt 组装 + JSON 输出
  - `GET /api/v1/ai/outreach/info` — 前端检测就绪状态
  - 自动识别 template_family（pet / feminine / general），按 family 选品牌摘要 + few-shots
  - 自动应用合规检查，返回 `compliance_flags` 给前台高亮
  - 走 `get_provider_for_feature("outreach_script")` — 你随时可在「设置 → AI 功能模型分配」给它单独换大模型，不影响 agent
- `~` 修正 `run.bat`：补回 `migrate_v6.py` 调用 + 新加 `migrate_v7.py`，同时把被 hook 反复改坏的 `>/dev/null` 改回 `>NUL`

### 验证结果（real LLM 调用）

| 测试 | 结果 |
|---|---|
| feminine 创作者 + 女性护理 SKU | family=feminine, 4 条女护 few-shots, 0 compliance flags, X9 Team 签名 |
| feminine 创作者 + 宠物 SKU | family=pet（按产品判定）, pet few-shot, outbox 写入成功 |
| 价格表 commission_rate_default 5% 的旧值被覆盖 | 实际生成话术里说"20% commission"（按 app_config 的 v1 默认） |
| 禁词 "100% leak-proof" / "FDA-approved" / "guaranteed sales" | 系统提示明确禁用，实际输出无命中 |

## 2026-05-07 — v3.3.0 (per-feature LLM 绑定)

- `+` 新表 `llm_feature`：每个 AI 功能独立绑定 Provider + 模型，互不影响
  - 预置 2 个功能：`agent`（操作 AI 助手）、`outreach_script`（邀约话术生成）
  - 不绑定时自动走"全局活跃 Provider"兜底
- `+` 5 个新端点（admin only）：
  - `GET /api/v1/llm/features` 列出所有功能 + 当前绑定 + 解析后实际使用的 Provider/Model
  - `GET /api/v1/llm/features/{code}` 单个功能详情
  - `PUT /api/v1/llm/features/{code}` 绑定到某个 Provider（含可选 model 覆盖）
  - `DELETE /api/v1/llm/features/{code}/binding` 解绑（回到全局兜底）
- `+` `app/llm.py` 新增 `get_provider_for_feature(code)` helper — 后续任何新 AI 功能调它即可
- `~` `app/agent.py` 改用 feature binding 解析 Provider（保留全局兜底兼容）
- `+` 前台 设置 → "AI 功能模型分配" 卡片式 UI（每个功能 1 张卡，下拉选 Provider + 输入模型 + 保存/解绑/启停）

## 2026-05-07 — v3.2.1 (AI 助手三个修复)

- `+` `/docs/{name}` HTML viewer：原 `[操作手册](docs/操作手册.md)` 链接 404 修复，现在自动渲染为带样式的 HTML 页面（含目录、代码块、表格、引用块），并防路径穿越（`../` 被拒）
- `+` 依赖：`pip install markdown`（用于服务端 .md → HTML 渲染，缺失时降级为纯文本预览）
- `~` 命名查询结果弹窗改为**卡片式渲染**（原 wide 表格在窄 modal 里显示不全）：
  - 单行也能完整看到所有非空字段
  - 自动识别 handle / tier / sku_code / id 显示在卡片头
  - URL 自动渲染成可点击链接，长内容自动截断 200 字
  - 最大 60vh 高度，超过自动滚动
- `+` **角色隔离**：agent 系统提示按用户角色分支
  - `admin`：可以引用源代码文件解释技术实现（`.py` / `schema.sql` / `.bat`）
  - `user` / `readonly`：**严格禁止**提及任何源代码 / 表名 / 字段名 / 实现细节，问到时统一回复"建议联系 zhang 或 liao"
  - 所有用户回答中只允许引用 `docs/*.md` 和前台界面操作

## 2026-05-07 — v3.2.0

- `+` **悬浮 AI 助手**（右下角 🤖 圆按钮，所有 tab 可见）
  - 点击展开 380×560 迷你聊天窗，与"🤖 AI 助手"完整 tab 共享对话历史
  - 后台收到回复时 FAB 上显示红点提示
  - 登录后自动出现，登出隐藏
- `+` **动作链接协议**：AI 回答里的蓝色按钮可点击直接跳转
  - `#nav:<view>` 切 tab
  - `#open:product:<sku>` / `#open:creator:<handle>` 直接打开编辑窗
  - `#run-query:<name>` 弹窗运行命名查询并显示结果表格
  - `#filter:<view>:<key>=<val>` 切 tab + 应用筛选条件
- `~` 升级 agent 系统提示，教 LLM 在合适场景嵌入动作链接（"答案 + 步骤 + 操作入口"三段式回答模板）

## 2026-05-07 — v3.1.0

- `+` **AI 项目管理员** (read-only consultant agent)
  - 新端点：`POST /api/v1/agent/chat` + `GET /api/v1/agent/info`
  - 加载 6 份运维文档（操作手册 / 协作约定 / API 指南 / schema / README / CHANGELOG，约 43 KB）作为系统提示
  - 走 LLM 配置中心激活的 Provider，廖那边代码不接触 Key
  - 硬性限制：永不回显 token / 永不假装代为操作 / 永不给业务决策 / 不知道就说不知道
- `+` 前端 "🤖 AI 助手" tab：聊天界面 + 4 个常见问题快捷入口 + token 用量显示 + 极简 markdown 渲染
- `+` 操作手册.md §6 改写为"AI 项目管理员"主题，原 LLM 配置中心降为 §6.5 子节

## 2026-05-07 — v3.0.3

- `+` `stop.bat` / `restart.bat`：解决 Windows + uvicorn `--reload` 留僵尸进程占端口的问题
- `+` `docs/操作手册.md`：完整运维手册，覆盖 8 大区域（启停 / 用户和权限 / Key 恢复 / 协作 / 数据维护 / LLM / 故障排查 / 灾难恢复）
- `+` README.md 顶部加快速链接索引

## 2026-05-07 — v3.0.2

- `+` `scripts/setup_personal_keys.py`：一次性把原 `.api_key` 转给廖 + 给张签发新 admin key
- `+` `.local_keys_backup.txt`：本地保存两人初始 key（已加入 `.gitignore`）
- `+` 自动维护 `.gitignore`：屏蔽 `.api_key` / `.local_keys_backup.txt` / `database.db` 等敏感文件

## 2026-05-07 — v3.0.1

- `+` `scripts/reset_user_key.py` + `reset_key.bat`：CLI 紧急重置 user key（管理员锁死自己时的兜底）
- `+` 协作约定文档加 "Key 丢失 / 重置 / 紧急恢复" 一节
- `~` `run.bat` 改进：迁移脚本始终运行（idempotent），不再仅在 db 不存在时才跑

## 2026-05-07 — v3.0.0 (BREAKING for auth model)

- `+` **多用户 RBAC**：单一 `.api_key` 改为 `api_user` + `api_key` 两表
  - 角色：`admin` (全权) / `user` (写数据,不动 schema) / `readonly` (只读)
  - Token 服务端只存 SHA-256 哈希，不可还原；签发时仅返回一次明文
  - 撤销机制：管理员可撤销任意用户的任意 Key，立即失效
  - `audit_log` 现在记录真实 username 而非空字符串
- `+` `/api/v1/auth/*` 全套用户管理接口
  - `GET /api/v1/auth/whoami` — 当前登录用户身份
  - `GET/POST/PATCH/DELETE /api/v1/auth/users[/{id}]` — 用户 CRUD (admin)
  - `GET/POST /api/v1/auth/users/{id}/keys` — 列/签发 Key (admin)
  - `DELETE /api/v1/auth/keys/{id}` — 撤销 Key (admin)
- `+` 前台登录浮层 + whoami 徽章 + 用户管理面板（admin 才能看到）
- `~` 写接口的角色门槛收紧：
  - 数据 CRUD (`/api/v1/data/*/bulk`, PATCH) → `user 或 admin`（readonly 403）
  - DDL (`/api/v1/tables*`, DELETE 数据/查询) → 仅 `admin`
  - LLM Provider 管理（含设 Key、激活、测试） → 仅 `admin`
  - LLM `/api/v1/llm/complete` → 任意已认证用户
- `+` 旧的 `.api_key` 文件**自动迁移**为张的第一把 admin key（你现有的脚本不会断）
- `+` 自动创建 `廖` 用户（admin 角色，无 Key）— 张登录后到设置签发即可
- 废弃 `require_api_key`（仍保留作 alias），新代码用 `require_authenticated` / `require_user_or_above` / `require_admin`

## 2026-05-07 — v2.2.0

- `+` 命名查询移到 DB (`_meta_query` 表)：加 / 改查询 不再需要重启服务
  - `POST /api/v1/queries` — 添加（自动 SQL 安全校验：仅 SELECT/WITH，禁多语句）
  - `PUT  /api/v1/queries/{name}` — 修改（含 builtin 的 override）
  - `DELETE /api/v1/queries/{name}` — 删除（builtin 不可删，只可改）
- `+` `run.bat` 启用 `--reload`：改 Python 代码 1-2s 自动热重启
- `+` SQL 安全：禁止 DELETE/DROP/UPDATE/INSERT 等非 SELECT 语句作为命名查询；禁多语句

## 2026-05-07 — v2.1.0

- `+` 新增 `/api/v1/llm/*` 配置中心：3 个内置 Provider (Anthropic / OpenAI / DeepSeek) + 自助加自定义 Provider
- `+` 新增 `POST /api/v1/llm/complete`：所有 AI 调用统一入口，廖不需要直接管 Key
- `+` 新增 `/api/v1/version` 端点：可被 poll 用于发现 schema 变化
- `+` `_meta_resource` 表新增 `deprecated_note` 列，软弃用机制就位

## 2026-05-07 — v2.0.0

- `+` 启用统一 `/api/v1/*` API，覆盖 7 个内置 resource (creators/products/outreach/...) + 6 个命名查询
- `+` 自助建表：`POST /api/v1/tables` + `POST /api/v1/tables/{name}/columns`
- `+` 通用 CRUD：`/api/v1/data/{resource}` 列表/查/批量upsert/PATCH/DELETE
- `+` 命名查询：`GET /api/v1/queries/{name}`，包含 `creators_to_contact`、`creators_follow_up`、`outreach_video_tracking`、`outreach_auth_pending`、`creators_by_tier`、`products_main_push`
- `-` 移除短暂存在过的 `/api/ingest/*` 端点（仅在内部测试期使用，未对外）

## 2026-05-06 — v1.0.0 (内部初版)

- `+` SQLite schema 建库：creator / product / outreach / product_image / category / staff / audit_log
- `+` 价格表 + 卖点 docx + 主推 SKU PDF 数据导入：44 个 SKU
- `+` 3 份每周表 + CM 评估表数据导入：66 个达人 / 101 条建联事件
- `+` 374 张实习生 A 社媒图片自动归类到 SKU
- `+` FastAPI 后端 + 单页前端管理界面 (`/`)
- `+` JSON / xlsx 导出脚本

---

## 模板（下次改动时复制下面这块到顶部）

```
## YYYY-MM-DD — vX.Y.Z

- `+` 加了什么
- `~` 改了什么 (如果是字段重命名，写清旧名 → 新名)
- `-` 删了什么 (如果是 deprecated 一段时间后删除，注明上次 deprecation 公告日期)
```
