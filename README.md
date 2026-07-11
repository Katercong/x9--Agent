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

可以通过 `DATABASE_URL` 切换数据库。MVP 代码保持 SQLAlchemy 兼容，后续可迁移 PostgreSQL。

## 常用接口

```text
POST /api/followup-agent/creators
POST /api/followup-agent/simulate-reply
POST /api/followup-agent/runs
GET  /api/followup-agent/runs/{run_id}
GET  /api/followup-agent/runs?creator_id=&inbound_reply_id=&limit=
GET  /health
```

## 测试

```powershell
pytest -q
```
