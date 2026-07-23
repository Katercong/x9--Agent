# 开发与运行指南

> 开发前请先阅读 [最终需求规格](final-requirements.md) 和 [实现缺口复盘](implementation-gap-review.md)。本文描述当前可运行的实现，不把规划功能写成已实现。

## 当前范围

当前系统由 FastAPI + SQLAlchemy + Pydantic 后端和 React Operator Workbench 组成，具备模拟入站、规则分类、异步 Agent run、LLM 草稿、人工审核、草稿交接和审计留痕。

当前不接入真实外部渠道，也没有自动发送能力。外接渠道尚未选定；模拟出站指令仅表示供人工处理的建议，绝不会实际发出消息。

容器化工作台、受控 demo seed 与启动方式见 [operator-workbench-demo.md](operator-workbench-demo.md) 和 [postgresql.md](postgresql.md)。

## 本地运行

### 1. 安装依赖与配置环境

```powershell
Set-Location C:\x92\x9_reply_agent_main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑未提交的 `.env`，设置原始 `POSTGRES_PASSWORD`、本机 `DATABASE_URL` 和容器 `DATABASE_URL_CONTAINER`，以及需要真实模型调用时的 `SILICONFLOW_API_KEY`。两条 URL 中的用户名/密码必须对 URL 保留字符进行百分号编码；密钥不得写入代码、测试、文档或提交记录。

PostgreSQL 的详细步骤见 [postgresql.md](postgresql.md)。未配置 `DATABASE_URL` 时，应用可使用可丢弃的 SQLite 开发库；生产环境必须使用 PostgreSQL。

### 2. 数据库、API 与 Worker

```powershell
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload
```

另开一个 PowerShell 窗口启动 Worker：

```powershell
python -m app.worker
```

只领取并处理一条队列任务：

```powershell
python -m app.worker --once
```

### 3. 测试与评测

```powershell
python -m pytest -q
```

真实模型评测需要显式传入 `--live`，结果只写入被 Git 忽略的 `evaluation_reports/`，不写业务数据库：

```powershell
$env:SILICONFLOW_MODEL='deepseek-ai/DeepSeek-V3.2'
python -m app.evaluation --suite pilot --prompt-version reply_followup_v2 --live
```

## 当前处理流程

```text
POST /simulate-reply
-> 模拟消息确定性幂等入库
-> 关键词规则分类
-> 终态分流或创建 queued run
-> Worker 领取任务
-> 上下文组装和 LLM JSON 输出
-> JSON + Pydantic 校验
-> run 留痕与 reply 进入 need_ai_review
-> 人工审核队列
-> 人工决定或终态只读待审
```

- 模拟消息的幂等键由部门、达人、方向、收发地址、主题和正文确定，并生成可重放的确定性 `external_message_id`。
- 真实渠道接入时必须使用 `channel + external_message_id`，且外部消息 ID 不能为空；当前没有真实渠道接收接口。
- 规则分类是权威输入。模型只能生成草稿、建议和审核理由，不得自动写回非终态业务状态。
- 退信进入 `ignored`，不创建 run 或普通跟进任务；明确拒绝仍是只读终态待审，不自动写入 `dropped`。DNC 可由人工确认永久阻断，或驳回并显式重新入队；待确认/已确认 DNC 会阻断新 run、草稿、导出和后续入站的 AI 处理。
- 明确退订还会在同一事务中把已有 `reply_followup_1` 的 `open/pending` 待办标记为 `blocked_dnc_pending`，避免人工沿历史待办继续联系。
- 普通回复仅允许最新且没有活跃后继的完成 run 形成最终决定；每条回复在数据库中最多一条决定，`reviewed` 后不可重新排队。
- 资料不足时，Worker 可以不调用模型而生成受限草稿，记录 `execution_status=succeeded`、`llm_status=skipped` 和 `block_reason=context_insufficient`，仍由人工审核。
- 未配置 `SILICONFLOW_API_KEY` 时，Worker 仍会处理 queued run：它使用本地受限 fallback，记录 `execution_status=succeeded` 与 `llm_status=not_configured`，不调用 Provider；配置 Key 后才调用真实模型。

## 核心数据模型

| 表/模型 | 职责 |
| --- | --- |
| `creators` / `Creator` | 达人档案、当前业务状态和 DNC 状态。 |
| `inbound_replies` / `InboundReply` | 入站回复、规则分类、处理状态和稳定幂等标识。 |
| `agent_followup_runs` / `AgentFollowupRun` | 每次模型任务的提示词、上下文、输出、错误、耗时和执行状态。 |
| `do_not_contact_confirmations` | 退订/DNC 的确认记录。 |
| `reference_materials` | 可版本化的政策、合作资料和报价条款。 |
| `simulated_outbound_instructions` | 仅用于模拟/人工交接的出站指令，不会发送。 |
| `creator_outreach_events` / `followup_tasks` | 沟通事件和人工待办。 |

关键约束：

- `inbound_replies.external_message_id` 非空；重复外部消息会被拒绝。
- `agent_followup_runs.creator_id`、`inbound_reply_id` 非空且受外键保护；孤儿 run 会被拒绝。
- 同一 `inbound_reply_id` 在 `queued` 或 `running` 状态最多存在一个 run（PostgreSQL 与 SQLite 均验证）。
- DNC、回复、待办、出站指令等审计关联均不使用级联删除；删除存在审计关联的达人或回复会被数据库拒绝。

## Worker 可靠性语义

1. Worker 在短事务中将 `queued` run 领取为 `running`，写入 `claim_token` 和 120 秒 `lease_expires_at` 后立即提交。
2. LLM 调用不持有数据库写锁。完成或失败回写必须同时匹配 run ID、`claim_token` 与 `running` 状态，旧 Worker 的延迟结果不能覆盖新状态。
3. 每次轮询先回收过期租约：run 记录为 `failed/worker_lost`，回复转入 `need_ai_review`。系统不自动重跑，人工必须显式新建 run。
4. Provider、JSON、Pydantic 之外的异常会记录为 `worker_unexpected_error`；错误摘要最多 500 字符且不保存堆栈。若异常回写失败，租约回收会作为兜底。
5. 查询接口可以读取 `block_reason` 和 `lease_expires_at`，但不会暴露 `claim_token`。

## 主要接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/followup-agent/creators` | 创建达人档案。 |
| `PATCH /api/followup-agent/creators/{creator_id}` | 局部更新达人档案。 |
| `POST /api/followup-agent/products` | 创建产品/活动资料。 |
| `PATCH /api/followup-agent/products/{product_id}` | 局部更新产品/活动资料。 |
| `POST /api/followup-agent/reference-materials` | 创建参考资料版本。 |
| `PATCH /api/followup-agent/reference-materials/{reference_key}` | 创建同一资料键的新版本。 |
| `POST /api/followup-agent/simulate-reply` | 模拟入站、幂等入库并按条件排队 Agent run。 |
| `POST /api/followup-agent/runs` | 对既有回复显式创建新的 Agent run。 |
| `GET /api/followup-agent/replies/{reply_id}` | 查询回复分类和处理状态。 |
| `GET /api/followup-agent/runs` | 查询 run 列表。 |
| `GET /api/followup-agent/runs/{run_id}` | 查询单个 run 的审计信息。 |
| `GET /api/followup-agent/review-queue` | 查询普通回复、模型失败、生成中、拒绝、DNC 或已批准草稿队列；支持 `reply_ready` 聚合。 |
| `GET /api/followup-agent/review-items/{reply_id}` | 读取单项队列结构、完整上下文和全部 Agent run 留痕，不写入数据。 |
| `POST /api/followup-agent/review-decisions` | 对普通回复批准最终草稿或关闭不使用草稿。 |
| `POST /api/followup-agent/review-items/{reply_id}/retry` | 对模型失败项显式重新入队；活跃 run 冲突返回 `409`。 |
| `POST /api/followup-agent/dnc-confirmations/{confirmation_id}/approve` | 人工确认 DNC 并永久阻断后续业务处理；不会发送消息。 |
| `POST /api/followup-agent/dnc-confirmations/{confirmation_id}/reject` | 人工驳回 DNC 并重新创建审核 run；不会发送消息。 |
| `GET /api/followup-agent/review-decisions/{decision_id}` | 查询人工决定及其草稿导出快照。 |
| `GET /api/followup-agent/review-decisions/{decision_id}/delivery-capability` | 返回只读交接能力边界，始终不提供系统发送。 |
| `POST /api/followup-agent/review-decisions/{decision_id}/exports` | 记录人工复制/导出的草稿快照；不会发送消息。 |
| `GET /api/followup-agent/outbound-instructions` | 查询模拟出站指令，不会触发发送。 |
| `GET /operator-workbench/` | 提供构建后的 React 人工审核工作台。 |
| `GET /health` | 健康检查。 |

## 提示词与模型

- 已验证的主力候选是 `deepseek-ai/DeepSeek-V3.2`，调用时传 `extra_body={"enable_thinking": false}`。
- V4 Flash 使用 `reasoning_effort=high`；该参数不能无条件传给 V3.2。
- V2 将规则分类视为权威输入，强制分类、动作、状态和人工审核映射；既有 24 条评测集上路由命中、JSON 和 Pydantic 均为 100%，P95 为 31.11 秒。
- 当前代码默认使用 V2 + DeepSeek V3.2；修改默认模型或提示词必须同时补充评测和回归测试。

## 变更纪律

1. 先核对最终需求与实现缺口，明确本次变更是补齐目标还是调整需求。
2. 数据库 schema 变更必须新增 Alembic migration，并同时覆盖 PostgreSQL 和 SQLite 约束测试。
3. 代码模块完成后先运行测试，提交前由负责人 review；提交信息使用中文。
4. `.env`、真实密钥、评测报告、可识别的业务数据和历史面试材料不得误纳入提交。
