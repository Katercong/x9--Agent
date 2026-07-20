# PostgreSQL 本地部署与迁移

> 本文说明当前仓库的本地 PostgreSQL 运行方式。生产目标和边界以 [最终需求规格](final-requirements.md) 为准；当前 Compose 只启动数据库，不代表 API 或 Worker 已完成生产容器化。

## 数据持久化与安全边界

PostgreSQL 由 Docker Compose 管理，数据保存在 Docker 命名卷 `x9-replychat_postgres_data`。删除容器不会删除数据卷；`docker compose down --volumes` 会清空本地数据库，只能用于确认可丢弃的数据。

服务只绑定 `127.0.0.1`，不会直接暴露到局域网。`.env` 已被 Git 忽略，真实密码、数据库 URL 和模型密钥不得写入代码或文档。

## 首次启动

1. 从 `.env.example` 创建本机 `.env`，设置新的 `POSTGRES_PASSWORD` 与对应的 `DATABASE_URL`。
   若密码含有 `@`、`:`、`/` 等 URL 保留字符，`DATABASE_URL` 中的密码部分必须进行百分号编码。
2. 启动数据库并确认其就绪：

   ```powershell
   docker compose up -d postgres
   docker compose ps
   ```

3. 安装依赖并应用 schema：

   ```powershell
   pip install -r requirements.txt
   alembic upgrade head
   ```

4. 启动 API 和单 Worker：

   ```powershell
   uvicorn app.main:app --reload
   python -m app.worker
   ```

## 日常操作

```powershell
docker compose logs -f postgres
docker compose stop postgres
docker compose start postgres
alembic current
alembic upgrade head
python -m pytest -q
```

所有 schema 修改必须先新增 Alembic migration，再执行 `alembic upgrade head`。应用启动不会自动建表或修改 PostgreSQL schema。

## 初始迁移的完整性约束

当前初始迁移已与 ORM 对齐，并在 PostgreSQL 与 SQLite 验证以下约束：

- `inbound_replies.external_message_id` 必填；重复稳定外部消息 ID 被拒绝。
- `agent_followup_runs.creator_id`、`inbound_reply_id` 必填且受外键约束；孤儿 run 被拒绝。
- 同一 `inbound_reply_id` 在 `execution_status IN ('queued', 'running')` 时最多一条 run。
- DNC、入站回复、人工待办、模拟出站指令等审计关联不使用 `ON DELETE CASCADE`；删除已有审计关联的 reply 或 creator 会被拒绝。

由于初始 migration 已存在，环境需要重新初始化时只可对可丢弃的本地库执行：

```powershell
docker compose down --volumes
docker compose up -d postgres
alembic upgrade head
```

执行前应再次确认目标不是需要保留的数据环境。

## 生产演进提醒

生产环境必须使用受管 PostgreSQL、受管 Secrets、备份恢复、监控和告警。未来 API、渠道同步 Worker 和 LLM Worker 将独立容器运行；多 Worker 领取任务时应采用 PostgreSQL 的 `FOR UPDATE SKIP LOCKED` 或等价原子机制。上述生产化工作尚未由当前 Compose 文件实现。
