# X9 ReplyChat Agent MVP 项目规划

## 1. 文档目的

这份文档是 `x9_ReplyChat_agent` 子项目的第一版规划文件，用来说明后续要做的 MVP 范围、数据表含义、基础流程、API 形态、测试方式和分模块 review 节奏。

当前模块一只产出这份规划文档，不实现后端代码，不新建数据库表，不启动项目服务，也不执行真实 LLM 调用。

后续每个模块都按下面节奏推进：

1. 完成一个小模块。
2. 跑该模块相关测试。
3. 停下来让人工 review。
4. review 通过后再提交一个独立 commit。

## 2. 项目目标

本 MVP 的目标是为 X9 达人建联流程增加一个“达人回复后辅助人工跟进”的 agent 小模块。

它不替代人工沟通，也不自动发送邮件。它的职责是：当达人回复后，帮助运营或 BD 快速判断达人意图、整理上下文、生成下一步跟进建议，并把每一次 agent 运行过程留痕，方便后续复盘和迭代。

第一版要打通的基础流程是：

```text
模拟回复入库
-> 规则分类
-> 构建上下文
-> LLM 生成建议
-> Pydantic 校验
-> run 留痕
-> 状态更新
```

后续项目可以迁移到 LangGraph，但 MVP 阶段先用当前项目已有的 `desktop/` FastAPI 后端实现。

## 3. 当前项目上下文

当前主线后端是：

```text
desktop/backend
```

它是当前项目的主要 FastAPI 后端，对外提供 `/api/local/*` 接口。

数据库层使用 SQLAlchemy。当前项目支持两类数据库：

- 本地默认 SQLite：`desktop/data/creators.sqlite`
- PostgreSQL：通过 `LOCAL_DB_URL` 环境变量连接

目前本地 shell 没有检测到 `LOCAL_DB_URL`，`15432` PostgreSQL 端口也没有监听。因此 MVP 开发和测试先以 SQLite 为默认，但代码需要保持 SQLAlchemy 兼容，后续可以切换到 PostgreSQL。

本项目已经有达人、建联邮件、Gmail 同步、邮件归档、跟进任务和状态事件等基础能力。因此本 MVP 的原则是优先复用现有表，不重复造已有业务表。

## 4. MVP 范围

第一版包含：

- 模拟达人回复入库。
- 对达人回复做规则分类。
- 从已有达人、邮件、事件、任务表中构建上下文。
- 有 OpenAI key 时调用 LLM 生成建议。
- 没有 OpenAI key 时使用确定性的模板降级建议。
- 用 Pydantic 校验 agent 输出。
- 将每次 agent 运行记录到 `agent_followup_runs`。
- 以受控方式维持达人进入待跟进状态。

第一版不包含：

- 不做前端 UI。
- 不自动发送邮件。
- 不让 LLM 直接决定最终业务状态。
- 不引入 LangGraph。
- 不新建重复的 `inbound_replies` 表。
- 不做批量自动扫描。
- 不做远程 creator 数字 ID 的完整桥接。

## 5. 数据表说明

这一节专门复述后续会用到的表名和含义，方便 review 时快速想起每张表负责什么。

### 5.1 `creators`

达人主表。

含义：系统里的达人档案。一行代表一个达人。

常见字段：

- `id`：达人主键。
- `platform`：达人所在平台，例如 TikTok、YouTube。
- `handle`：达人账号名。
- `display_name`：达人展示名。
- `profile_url`：达人主页链接。
- `bio`：达人简介。
- `email`：达人邮箱。
- `followers_count`：粉丝数。
- `department_code`：所属部门。
- `owner_bd`：当前负责跟进的人。
- `current_status`：当前建联或合作状态。
- `recommendation_reason`：推荐原因。
- `recommended_product_type`：推荐产品方向。
- `recommended_collab_type`：推荐合作方式。

在本 MVP 中，agent 会读取 `creators` 来构建上下文，例如达人是谁、之前推荐理由是什么、当前处于什么状态。

第一版 agent 不会随意自动修改 `creators.current_status`。状态推进需要遵守当前项目已有的建联流程。

### 5.2 `creator_email_messages`

达人邮件消息表。

含义：保存 Gmail 同步到的达人邮件会话消息，尤其是达人回复。

它在本 MVP 中承担“入站回复表”的角色。也就是说，你最初提到的 `inbound_replies` 在第一版里不单独建表，而是指 `creator_email_messages` 里 `direction="inbound"` 的记录。

常见字段：

- `id`：邮件消息主键。
- `creator_id`：关联的达人 ID。
- `outreach_email_id`：关联的已发送建联邮件。
- `gmail_account_id`：同步该邮件的 Gmail 账号。
- `gmail_thread_id`：Gmail 会话 ID。
- `gmail_message_id`：Gmail 消息 ID。
- `direction`：消息方向，常见值为 `inbound` 或 `bounce`。
- `from_email`：发件人。
- `to_email`：收件人。
- `subject`：邮件主题。
- `snippet`：Gmail 摘要。
- `body_preview`：正文预览。
- `body`：正文内容。
- `body_format`：正文格式，例如 `plain` 或 `html`。
- `message_at`：消息发生时间。
- `metadata_json`：额外元数据。

MVP 中的“模拟回复入库”就是向这张表插入一条 `direction="inbound"` 的消息。

### 5.3 `outreach_emails`

建联邮件表。

含义：保存系统生成、编辑、发送的建联邮件，也包括后续人工回复邮件。

常见字段：

- `id`：邮件主键。
- `creator_id`：关联达人。
- `to_email`：收件人。
- `from_email`：发件人。
- `subject`：邮件主题。
- `body`：邮件正文。
- `body_format`：正文格式，例如 `plain` 或 `html`。
- `status`：邮件状态，例如 `draft`、`queued`、`sent`、`failed`。
- `gmail_message_id`：Gmail 消息 ID。
- `gmail_thread_id`：Gmail 会话 ID。
- `parent_email_id`：如果是跟进回复，可关联上一封邮件。
- `context_json`：生成邮件时使用的上下文快照。

MVP 中 agent 会参考历史 `outreach_emails`，理解之前我们给达人发过什么、最近一封邮件是什么内容、这次回复属于哪个会话。

### 5.4 `creator_outreach_events`

达人建联事件流水表。

含义：记录达人建联生命周期中的关键事件，是 append-only 的事件日志。

常见事件：

- `recommended`：被推荐。
- `assigned`：已分配负责人。
- `sent`：已发送建联邮件。
- `pending_followup`：达人有回复，需要跟进。
- `pending_reply`：等待或待处理回复。
- `contacted`：已建联。
- `replied`：达人已回复。
- `communicating`：沟通中。
- `confirmed`：确认合作。
- `sample_shipped`：已寄样。
- `sample_delivered`：样品签收。
- `video_published`：视频已发布。
- `partnered`：已合作。
- `ad_authorized`：广告授权。
- `ad_running`：广告投放中。
- `dropped`：放弃或不继续。

MVP 中，当模拟入站回复创建后，会沿用现有逻辑确保达人进入待跟进状态。agent 本身不会直接把达人推进到成交、拒绝等最终状态。

### 5.5 `followup_tasks`

人工跟进任务表。

含义：系统生成给运营或 BD 的待办任务。

常见字段：

- `id`：任务主键。
- `creator_id`：关联达人。
- `department_code`：所属部门。
- `owner_user_id`：任务负责人。
- `task_type`：任务类型，例如 `reply_followup_1`。
- `status`：任务状态，例如 `open`、`pending`、`completed`。
- `due_at`：任务截止时间。
- `completed_at`：任务完成时间。
- `priority`：优先级。
- `reason`：生成任务原因。
- `metadata_json`：额外信息。

MVP 中，达人回复入库后可以复用现有逻辑创建或保持待跟进任务。agent 只提供建议，不替代任务完成动作。

### 5.6 `agent_followup_runs`

本 MVP 计划新增的 agent 运行留痕表。

含义：记录每一次 Follow-up Agent 对某条达人回复的分析过程和结果。

计划字段：

- `id`：run 主键。
- `department_code`：部门。
- `creator_id`：关联达人。
- `inbound_message_id`：关联的入站消息，也就是 `creator_email_messages.id`。
- `reply_category`：规则分类结果。
- `suggested_status`：agent 建议状态。
- `llm_status`：LLM 状态，例如 `generated`、`fallback`、`not_configured`、`error`。
- `context_json`：本次构建的上下文快照。
- `output_json`：Pydantic 校验后的建议结果。
- `validation_error`：校验失败信息。
- `created_by`：触发 agent 的用户。
- `created_at`：创建时间。
- `updated_at`：更新时间。

这张表是 MVP 的核心留痕表，方便后续复盘“为什么 agent 给了这个建议”。

## 6. MVP 流程设计

### 6.1 模拟回复入库

计划新增接口：

```text
POST /api/local/followup-agent/simulate-reply
```

作用：

- 选择一个已有达人。
- 模拟达人回复内容。
- 写入 `creator_email_messages`。
- 可选立即运行 agent。

这一步用于 MVP 开发和测试，不依赖真实 Gmail 同步。

### 6.2 规则分类

先用规则对回复做初步分类。

第一版分类：

- `interested`：达人表达合作兴趣。
- `need_more_info`：达人需要更多信息。
- `negotiation`：达人在谈价格、佣金、样品、合作条件。
- `not_interested`：达人明确拒绝。
- `bounce_or_invalid`：退信、地址无效、无法送达。
- `unclear`：信息不足，无法判断。

规则分类的作用：

- 给 LLM 一个稳定的先验。
- 没有 LLM key 时也能生成可用建议。
- 方便测试，不把所有判断都交给模型。

### 6.3 构建上下文

上下文来自：

- `creators`：达人基础信息、当前状态、推荐理由、推荐产品和合作方式。
- `creator_email_messages`：本次达人回复内容。
- `outreach_emails`：历史建联邮件和上一封相关邮件。
- `creator_outreach_events`：最近建联事件。
- `followup_tasks`：当前是否已有待跟进任务。

上下文需要保存到：

```text
agent_followup_runs.context_json
```

这样后续能复盘 agent 的判断依据。

### 6.4 LLM 生成建议

有 `OPENAI_API_KEY` 时调用 OpenAI Chat Completions。

没有 key 时使用规则模板降级生成建议，并设置：

```text
llm_status = "not_configured"
```

输出内容包括：

- `reply_category`：回复分类。
- `suggested_reply`：建议人工回复话术。
- `next_action`：下一步动作建议。
- `suggested_status`：建议状态。
- `confidence`：置信度。
- `warnings`：注意事项。
- `reasoning_summary`：简短解释。

LLM 不能直接写业务状态，只能输出建议。

### 6.5 Pydantic 校验

用 Pydantic 定义 agent 输出结构，保证字段稳定。

如果校验成功：

- 写入 `agent_followup_runs.output_json`。
- API 返回结构化建议。

如果校验失败：

- 写入 `agent_followup_runs.validation_error`。
- API 返回错误。
- 不进行后续状态处理。

### 6.6 Run 留痕

每次 agent 运行都必须写入 `agent_followup_runs`。

即使 LLM 不可用，也要留痕：

- 使用了什么上下文。
- 分类结果是什么。
- 是否走了降级模板。
- 最终建议是什么。

### 6.7 状态更新

MVP 第一版采用受控状态策略：

- 入站回复入库后，确保达人处于待跟进状态。
- agent run 只记录建议，不自动把达人改成 `communicating`、`dropped` 等状态。
- 真正的人为回复发送后，继续沿用现有 `outreach` 流程推进状态。

这样可以避免 LLM 误判直接污染业务状态。

## 7. API 设计草案

### 7.1 模拟回复接口

```text
POST /api/local/followup-agent/simulate-reply
```

请求示例：

```json
{
  "creator_id": "creator_123",
  "from_email": "creator@example.com",
  "subject": "Re: Collaboration",
  "body": "Sounds interesting. Can you send more details?",
  "run_agent": true
}
```

返回示例：

```json
{
  "ok": true,
  "message": {
    "id": "cem_123",
    "creator_id": "creator_123",
    "direction": "inbound"
  },
  "run": {
    "id": "afr_123",
    "reply_category": "need_more_info"
  }
}
```

### 7.2 运行 Agent 接口

```text
POST /api/local/followup-agent/runs
```

请求示例：

```json
{
  "inbound_message_id": "cem_123"
}
```

返回示例：

```json
{
  "ok": true,
  "run": {
    "id": "afr_123",
    "creator_id": "creator_123",
    "reply_category": "need_more_info",
    "llm_status": "not_configured",
    "output": {
      "suggested_reply": "Thanks for your reply. I will send more campaign details here.",
      "next_action": "send_campaign_details",
      "suggested_status": "pending_followup",
      "confidence": 0.82,
      "warnings": [],
      "reasoning_summary": "The creator showed interest but asked for more details."
    }
  }
}
```

### 7.3 查询单次 Run

```text
GET /api/local/followup-agent/runs/{run_id}
```

用途：查询单次 agent 运行记录。

### 7.4 查询 Run 列表

```text
GET /api/local/followup-agent/runs?creator_id=&inbound_message_id=&limit=
```

用途：按达人、入站消息或时间查询 agent 运行记录。

## 8. 分阶段实施节奏

### 模块 1：规划文档

内容：

- 新增 `x9_ReplyChat_agent/PROJECT_SPEC.md`。
- 记录本 MVP 的范围、流程、表含义、接口设计、测试计划。

测试：

- 不需要跑后端测试。
- 人工 review 文档即可。

commit：

```text
docs: add followup agent mvp spec
```

### 模块 2：Run 模型和表注册

内容：

- 新增 `AgentFollowupRun`。
- 注册到 models。
- 加入当前项目的 `create_all` 或幂等 schema ensure 流程。
- 加入 `/api/local/data` 只读映射。

测试：

- 验证 `init_db()` 后表可创建。
- 验证模型字段可写入和读取。

commit：

```text
feat: add followup agent run model
```

### 模块 3：规则分类和上下文构建

内容：

- 新增 `classify_reply`。
- 新增 `build_followup_context`。
- 覆盖常见回复类型测试。

测试场景：

- `interested`
- `need_more_info`
- `negotiation`
- `not_interested`
- `bounce_or_invalid`
- `unclear`
- 上下文包含 creator、inbound message、历史邮件

commit：

```text
feat: classify inbound replies for followup agent
```

### 模块 4：建议生成、校验和留痕

内容：

- 新增 Pydantic 输出 schema。
- 新增 LLM 调用和无 key 降级逻辑。
- 新增 `persist_run`。
- 保存 `context_json` 和 `output_json`。

测试场景：

- 无 OpenAI key 时返回确定性 fallback。
- mock LLM 返回合法 JSON 时校验通过。
- mock LLM 返回非法 JSON 时记录 `validation_error`。

commit：

```text
feat: generate followup agent suggestions
```

### 模块 5：FastAPI 接口

内容：

- 新增 router。
- 接入 `desktop.backend.main`。
- 实现模拟回复、运行 agent、查询 run。

测试场景：

- 模拟回复入库成功。
- 单条 agent run 成功。
- 部门权限隔离生效。
- run 可查询。

commit：

```text
feat: expose followup agent api
```

## 9. 测试计划

每个模块完成后只跑相关测试，测试通过后给人工 review。

最终后端验证命令：

```powershell
py -3.11 -m pytest desktop\backend\tests\test_followup_agent.py desktop\backend\tests\test_outreach.py -q
```

可选本地 smoke：

```powershell
.\start_all.ps1 -NoBrowser
```

然后验证：

- `/health`
- 登录态接口
- 模拟回复接口
- agent run 接口
- run 查询接口

## 10. 后续演进方向

MVP 稳定后可以继续做：

- 接入前端跟进页面。
- Gmail 同步后自动触发 agent。
- 批量扫描未处理回复。
- LangGraph 化流程节点。
- 人工采纳或拒绝建议的反馈记录。
- prompt 版本管理。
- 多语言回复策略。
- 更完整的达人合作阶段判断。

## 11. 模块一验收标准

模块一完成后应满足：

- `x9_ReplyChat_agent/PROJECT_SPEC.md` 存在。
- 文档明确说明当前只做规划，不做后端实现。
- 文档说明 MVP 流程和每个阶段的职责。
- 文档解释所有关键表名的含义。
- 文档记录后续模块拆分、测试方式和 commit 节奏。
- 不修改后端代码。
- 不新增数据库表。
- 不启动项目服务。
