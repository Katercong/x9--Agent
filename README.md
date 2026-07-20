# X9 ReplyChat Agent

面向内部 BD/运营团队的达人回复跟进辅助 Agent。系统只负责规则分类、上下文整理、AI 草稿和下一步建议；除人工确认的操作外，系统不会向任何外接渠道自动发送消息。

## 文档入口

完整的开发与交接资料已归档到 [docs/README.md](docs/README.md)。开始任何需求、代码、数据模型或部署变更前，必须先阅读 [最终需求规格](docs/final-requirements.md)，并用 [实现缺口复盘](docs/implementation-gap-review.md) 确认当前范围。

## 快速开始（本地）

```powershell
pip install -r requirements.txt
docker compose up -d postgres
alembic upgrade head
uvicorn app.main:app --reload
```

另开一个终端启动 Worker：

```powershell
python -m app.worker
```

运行测试：

```powershell
python -m pytest -q
```

本地 PostgreSQL、环境变量和 Alembic 操作见 [PostgreSQL 部署说明](docs/postgresql.md)。真实密钥只可放在未提交的 `.env` 中。
