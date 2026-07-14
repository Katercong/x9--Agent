# 达人回复跟进 Agent：项目交接与进度记录

> 最后更新：2026-07-14
>
> 本文供后续接手的开发者或 AI 助手快速理解项目。不要在本文、代码或提交记录中写入真实 API Key、达人邮箱或其他生产数据。

## 1. 项目目标与业务边界

这是一个面向内部运营人员的“达人回复跟进辅助 Agent”MVP。它接收达人入站回复，完成规则分类、上下文拼装、LLM 草稿建议、留痕与人工待办辅助。

当前业务原则：

- AI 只生成建议与草稿，不自动发送外部消息，不自动将建议状态应用到达人档案。
- 除明确退订、明确拒绝和退信等终态分流外，所有达人沟通均由人工确认后继续推进。
- 明确退订进入 DNC（Do Not Contact，禁止联系）专表；后续采集或回复进入时应先查询该表决定是否跳过。
- 明确拒绝进入 `dropped`，不创建普通跟进任务；若达人后续重新表达合作意向，才进入人工确认后恢复。
- 当前只模拟入站和出站，不接 Gmail、社媒或其他真实外部渠道。

## 2. 当前流程完成度

### 已完成

```text
模拟回复幂等入库
-> 规则关键词分类并写回回复表
-> ignored / dropped / need_ai_review 等状态分流
-> 拼装达人、产品、聊天历史、参考资料上下文
-> 创建异步 Agent run（queued）
-> 单 Worker 轮询并调用 LLM
-> JSON 解析与 Pydantic 校验
-> run、提示词、上下文、输出、错误和成本留痕
-> 建议状态与人工审核状态更新
-> 拒绝/退订的模拟出站指令或 DNC 留痕
```

### 仍在完善

- 将“所有非自动 DNC 都必须人工确认”的业务规则落实为服务端硬约束，不能仅依赖模型的 `requires_human_review` 输出。
- 用完整评测集复核 V2 提示词的人工复核标记，并扩展人工可用性评分。
- 将评测脚本改为异步 Worker 实际路径并支持逐条 checkpoint，避免长测中断后没有部分报告。
- 未来迁移 PostgreSQL、引入 Alembic、接入真实渠道、鉴权/后台 UI、监控告警与并发任务队列。

## 3. 技术架构

- Web：FastAPI，入口为 `app/main.py`。
- 数据：SQLAlchemy + SQLite MVP；开发库可重建。生产迁移 PostgreSQL 时需改用 Alembic。
- 校验：Pydantic，核心建议结构为 `app/schemas.py` 的 `AgentSuggestion`。
- 模型：硅基流动 OpenAI 兼容接口，封装在 `app/llm.py`。
- 异步执行：数据库 `queued` run + `python -m app.worker` 单 Worker 轮询，不依赖 Redis。
- 测试：pytest，主测试文件为 `tests/test_followup_agent.py`。

## 4. 核心数据表含义

| 表/模型 | 含义 |
| --- | --- |
| `creators` / `Creator` | 达人档案、当前业务状态、达人画像与推荐信息。|
| `inbound_replies` / `InboundReply` | 达人入站回复及分类、处理状态、幂等字段。|
| `agent_followup_runs` / `AgentFollowupRun` | 每次 Agent 建议任务的执行状态、提示词、上下文快照、原始输出、错误和耗时。|
| `do_not_contact_confirmations` / `DoNotContactConfirmation` | 明确退订/禁止联系的专表，用于后续采集前过滤。|
| `reference_materials` / `ReferenceMaterial` | 可版本化的公司政策、合作详情、报价条款等已批准资料。|
| `simulated_outbound_instructions` / `SimulatedOutboundInstruction` | 仅模拟的外发动作指令，不会真的发送。|
| `creator_outreach_events` / `CreatorOutreachEvent` | 与达人沟通、状态变化等业务事件留痕。|

`InboundReply` 的联合唯一约束为：
`department_code + creator_id + direction + from_email + to_email + subject + body`。

这是 SQLite MVP 的内容去重方案。真实渠道接入后应优先增加 `channel + external_message_id` 作为稳定幂等键；内容唯一约束只保留为兜底或模拟逻辑。

## 5. 关键接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/followup-agent/creators` | 创建达人。|
| `PATCH /api/followup-agent/creators/{creator_id}` | 局部更新达人，避免 PUT 语义造成档案字段被静默清空。|
| `POST /api/followup-agent/products` | 创建产品/活动资料。|
| `PATCH /api/followup-agent/products/{product_id}` | 局部更新产品/活动资料。|
| `POST /api/followup-agent/reference-materials` | 创建已批准的公司或活动参考资料。|
| `PATCH /api/followup-agent/reference-materials/{reference_key}` | 创建同一资料键的新版本。|
| `GET /api/followup-agent/reference-materials` | 查询参考资料及版本。|
| `POST /api/followup-agent/simulate-reply` | 模拟入站回复、幂等入库和可选 Agent 排队。|
| `POST /api/followup-agent/runs` | 对既有回复显式补跑 Agent。|
| `GET /api/followup-agent/replies/{reply_id}` | 查看回复分类和处理状态。|
| `GET /api/followup-agent/runs/{run_id}` | 查看单次 run 留痕。|
| `GET /api/followup-agent/runs` | 查询 run 列表。|
| `GET /api/followup-agent/outbound-instructions` | 查看模拟外发指令。|

## 6. 提示词版本与评测结论

### V1：`reply_followup_v1`

V1 只要求模型使用上下文、不编造、信息不完整或有风险时保留人工复核，并附带 JSON Schema。它没有把规则层分类设为权威输入，也没有强制分类到动作/状态/人工复核的映射。

使用 `deepseek-ai/DeepSeek-V3.2` 且 `enable_thinking=false` 的 24 条评测结果：

- JSON 解析：100%（24/24）
- Pydantic 校验：100%（24/24）
- 路由完全命中：33.33%
- 漏掉人工复核标记：24 条
- P95 延迟：33.50 秒

结论：结构化输出稳定，但路由与人工审核边界不符合业务要求。

### V2：`reply_followup_v2`

V2 在 V1 基础上增加：

1. `Authoritative rule category`：规则层分类是权威值，模型必须原样写入 `reply_category`。
2. 六类固定路由：每个分类明确对应 `next_action`、`suggested_status` 和 `requires_human_review=true`。
3. 合作资料约束：只可使用上下文中存在的时间线、交付物和预算信息；缺失时不得编造，必须提示人工复核。

同一模型、同一 24 条样本的 V2 结果：

- JSON 解析：100%（24/24）
- Pydantic 校验：100%（24/24）
- 路由完全命中：100%（24/24）
- 漏掉人工复核标记：1 条（`pilot_unclear_en_03`）
- P95 延迟：31.11 秒

评测报告位于 Git 忽略目录 `evaluation_reports/`：

- `pilot_reply_followup_v1_20260714_170634.json`
- `pilot_reply_followup_v2_20260714_172012.json`

注意：V2 已证明提示词可以显著提升模型输出的一致性，但最终人工审核策略仍应由服务端兜底。

## 7. 当前模型配置

推荐当前继续验证的主力模型：

```env
SILICONFLOW_MODEL=deepseek-ai/DeepSeek-V3.2
```

`app/llm.py` 中的模型参数约定：

- `deepseek-ai/DeepSeek-V4-Flash`：使用 `reasoning_effort=high`。Provider 会将低/中思考映射到高档。
- `deepseek-ai/DeepSeek-V3.2` 与 `Pro/deepseek-ai/DeepSeek-V3.2`：使用 `extra_body={"enable_thinking": false}`。
- 所有模型仍请求 JSON Mode，并在本地继续执行 JSON 解析和 Pydantic 校验。

不要把 `.env` 加入 Git；真实密钥只放在本机 `.env`。

## 8. 当前工作区与提交状态

已推送的最近功能提交包括：

- `785fb22 feat: 新增LLM异步任务和轮询Worker`
- `4cf84f5 feat: 按回复价值控制LLM调用和成本留痕`
- `42d34f6 feat: 新增合作参考资料版本管理和提示词快照`
- `dec65c9 feat: 新增拒绝分流和模拟出站指令`
- `c3c07c5 test: 完善异步LLM流程评测和运行说明`

截至本文更新，以下改动尚未人工 review、提交或推送：

- `app/llm.py`：按模型选择 V4 的思考强度参数或 V3.2 的关闭思考参数。
- `tests/test_followup_agent.py`：V3.2 参数分支的回归测试。
- `PROJECT_HANDOFF.md`：本交接文档。

另外，工作区可能有未跟踪的 LLM 复盘 Word 文档；它们不是本次代码提交的一部分，提交前不要误加入暂存区。

## 9. 常用命令

```powershell
# 进入项目目录
Set-Location C:\x92\x9_reply_agent_main

# 运行测试
python -m pytest -q

# 启动 API
uvicorn app.main:app --reload

# 启动单 Worker
python -m app.worker

# 运行 24 条真实评测（会消耗 API token，但不写业务数据库）
$env:SILICONFLOW_MODEL='deepseek-ai/DeepSeek-V3.2'
python -m app.evaluation --suite pilot --prompt-version reply_followup_v2 --live
```

## 10. 下一步建议顺序

1. 人工 review 当前 V3.2 参数改动、V2 评测结论和本文。
2. 服务端强制非终态建议进入人工审核，避免模型漏写 `requires_human_review` 时违反业务规则。
3. 将 V2 设为主提示词版本后补充回归测试，特别覆盖 `unclear` 的人工审核场景。
4. 扩展评测集与人工评分表，重点检查报价、资料缺失、语气、事实幻觉和多轮上下文。
5. 再考虑 PostgreSQL/Alembic 与真实渠道接入。
