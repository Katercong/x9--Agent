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

`POST /api/followup-agent/simulate-reply` 对同一封模拟回复是幂等的。它使用部门、达人、
收发邮箱、主题和正文联合判断重复；首次响应 `duplicate=false`，重复请求返回已有回复和
已有 run，且不会重复创建事件或待办。若首次请求未运行 Agent，后续相同请求带
`run_agent=true` 时会补跑一次。已标记为 `ignored` 的回复不能通过 `/runs` 再次运行。

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
POST /api/followup-agent/simulate-reply
POST /api/followup-agent/runs
GET  /api/followup-agent/replies/{reply_id}
GET  /api/followup-agent/runs/{run_id}
GET  /api/followup-agent/runs?creator_id=&inbound_reply_id=&limit=
GET  /health
```

## 测试

```powershell
pytest -q
```
