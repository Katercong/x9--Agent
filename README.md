# X9 ReplyChat Agent

达人回复跟进辅助 Agent 的独立 MVP 项目。

它用于在达人回复后辅助人工 BD/运营判断意图、整理上下文、生成下一步跟进建议，并把每次运行过程写入 `agent_followup_runs` 留痕表。

## MVP 流程

```text
模拟回复入库
-> 规则分类
-> 构建上下文
-> 生成建议
-> Pydantic 校验
-> run 留痕
-> 状态更新
```

## 数据表说明

- `creators`：达人主表，一行代表一个达人。
- `do_not_contact_confirmations`：DNC 审核流水表，保存退订请求和人工确认结果。
- `products`：产品档案表，按 `product_type` 为达人回复提供产品信息。
- `inbound_replies`：入站回复表，MVP 独立版用它承接达人回复。
- `outreach_emails`：历史建联邮件表，用于构建上下文。
- `creator_outreach_events`：达人建联事件流水表。
- `followup_tasks`：人工跟进待办表。
- `agent_followup_runs`：Agent 每次运行的上下文、输出、LLM 状态和校验结果留痕表。

`inbound_replies.processing_status` 表示回复处理进度：

- `new`：已入库和分类，尚未完成 Agent 建议处理。
- `ignored`：规则判定为退信或无效地址，不进入建议生成。
- `need_ai_review`：分类或建议置信度不足，需要人工复核。
- `suggestion_ready`：建议已生成并通过当前 MVP 的置信度门槛。

回复意图另存于 `reply_category`，规则置信度、命中原因和分类时间分别记录在
`classification_confidence`、`classification_reason` 和 `classified_at`。

建议生成先要求 JSON 可解析，再由 Pydantic 校验字段。若生成结果不是 JSON，run 会记录
`llm_status=invalid_json`；若 JSON 字段不符合建议结构，会记录
`llm_status=validation_failed`。两类失败都会保留原始输出和校验错误，并将回复转为
`need_ai_review`。

规则或建议任一置信度低于 `0.70` 时会进入人工复核。对 `interested`、`need_more_info`、
`negotiation` 三类回复，达人缺少 `bio` 和 `recommendation_reason`，或缺少
`recommended_product_type` 时，也会在建议的 `warnings` 中标记缺失项并进入人工复核。

达人明确拒绝合作时，系统将达人状态设为 `dropped`，不会新建回复跟进待办，并取消已有的
`reply_followup_1` 未完成待办。若回复含明确退订表达（如 `unsubscribe`、`remove me`、
`退订`、`不要再联系`），系统会创建一条 `do_not_contact_confirmations` 待确认流水，并将达人标记为
`do_not_contact_status=pending_confirmation`。确认表以 `(creator_id, status)` 建立复合索引，保留审核历史；
后续采集和建联应直接查询达人主表的当前 DNC 状态，跳过 `confirmed` 达人。

`POST /api/followup-agent/simulate-reply` 对同一封模拟回复是幂等的。模拟消息固定标记为
`channel=simulation` 且没有 `external_message_id`，使用部门、达人、收发邮箱、主题和正文
进行内容去重；首次响应 `duplicate=false`，重复请求返回已有回复和已有 run，且不会重复创建
事件或待办。若首次请求未运行 Agent，后续相同请求带 `run_agent=true` 时会补跑一次。
已标记为 `ignored` 的回复不能通过 `/runs` 再次运行。

未来真实渠道接入应写入非空的 `channel` 和上游稳定的 `external_message_id`。数据库以
`department_code + channel + external_message_id` 保证真实消息幂等；相同正文但不同外部消息 ID
可以同时存在。本轮尚未提供真实消息接收接口。

产品档案通过达人 `recommended_product_type` 匹配。只有启用中的产品会进入 Agent 上下文；
未匹配或未启用时，合作相关回复会标记 `missing_product_context` 并转人工复核。
上下文还会保留当前回复以外最近 5 条历史入站回复，用于后续提示词拼装。

每次 Agent run 会生成 `reply_followup_v1` PromptPackage，并保存已脱敏、已截断后的最终 prompt。
提示词包含产品、达人公开档案摘要、当前回复、双向历史消息、事件和待办；邮箱、主页 URL 与
正文中的邮箱/URL 会被替换为脱敏标记。当前回复优先保留，最终 prompt 最大为 `12,000` 字符。
本轮仅建设提示词工厂，fallback 仍未调用真实 LLM。后续接入真实 LLM 时，生成器会接收完整的
`PromptPackage`，并须在 JSON 建议中返回 `requires_human_review`（是否必须人工复核）与
`review_reasons`（复核原因列表）。这两个字段会与上下文缺失告警合并为 `warnings`，任一项要求复核时，
回复状态都会进入 `need_ai_review`。

建议中的 `next_action` 只能是 `send_campaign_details`、`clarify_terms`、
`acknowledge_and_close`、`ask_clarifying_question` 或 `verify_contact_method`。该集合由
Pydantic `Literal` 与提示词中的 JSON Schema 共用；Provider 返回未知动作时会记录为
`validation_failed`，并转入人工复核。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认使用 SQLite：

```text
sqlite:///./data/replychat_agent.sqlite
```

当前 MVP 尚未引入数据库迁移。若本地已经运行过旧版本，升级模型字段后请先重建可丢弃的开发库：

```powershell
Remove-Item -LiteralPath .\data\replychat_agent.sqlite -ErrorAction SilentlyContinue
```

下次启动服务时会按最新模型自动建表。请勿对需要保留数据的数据库执行该命令。

可以通过 `DATABASE_URL` 切换数据库。MVP 代码保持 SQLAlchemy 兼容，后续可迁移 PostgreSQL。

## 常用接口

```text
POST /api/followup-agent/creators
PUT  /api/followup-agent/creators/{creator_id}
PATCH /api/followup-agent/creators/{creator_id}
POST /api/followup-agent/products
PUT  /api/followup-agent/products/{product_id}
PATCH /api/followup-agent/products/{product_id}
POST /api/followup-agent/simulate-reply
POST /api/followup-agent/runs
GET  /api/followup-agent/replies/{reply_id}
GET  /api/followup-agent/runs/{run_id}
GET  /api/followup-agent/runs?creator_id=&inbound_reply_id=&limit=
GET  /health
```

达人档案接口语义：`POST /creators` 只创建，成功返回 `201`，重复 ID 返回 `409`；
`PUT /creators/{creator_id}` 需要提交完整档案并替换可编辑字段；
`PATCH /creators/{creator_id}` 只更新请求中显式提供的字段，未提供字段保持不变。
在 PATCH 中显式传入 `null` 会清空对应可空档案字段。PUT/PATCH 对不存在的达人返回 `404`。
达人当前跟进状态和 DNC 状态由回复流程维护，不接受档案接口直接修改。

产品接口同样采用明确语义：POST 创建产品，PUT 完整替换，PATCH 仅更新显式字段；
产品类型在产品档案中唯一。

## 测试

```powershell
pytest -q
```
