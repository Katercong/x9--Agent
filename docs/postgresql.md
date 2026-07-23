# PostgreSQL 本地部署、容器化工作台与迁移

> 本文说明当前仓库的本地 PostgreSQL 和容器化工作台运行方式。生产目标和边界以 [最终需求规格](final-requirements.md) 为准；当前 Compose 用于本地演示，不等同于受管生产部署。

## 数据持久化与安全边界

PostgreSQL 由 Docker Compose 管理，数据保存在 Docker 命名卷 `x9-replychat_postgres_data`。默认 Compose 会启动 PostgreSQL、一次性 Alembic `migrate` 和 FastAPI `api`；`worker` 和 `demo-seed` 仅在显式 profile 中运行。删除容器不会删除数据卷；`docker compose down --volumes` 会清空本地数据库，只能用于确认可丢弃的数据。

服务只绑定 `127.0.0.1`，不会直接暴露到局域网。`.env` 已被 Git 忽略，真实密码、数据库 URL 和模型密钥不得写入代码或文档。

## 首次启动

1. 从 `.env.example` 创建本机 `.env`，设置新的原始 `POSTGRES_PASSWORD`，以及两条已编码连接 URL：
   `DATABASE_URL` 供本机 Uvicorn/Alembic 使用，主机为 `127.0.0.1`；`DATABASE_URL_CONTAINER` 供 Compose 的 migrate、API、Worker 和 demo seed 使用，主机为 `postgres`。
   若用户名或密码含 `@`、`:`、`/` 等 URL 保留字符，必须在两条 URL 中分别进行百分号编码；不要把原始 `POSTGRES_PASSWORD` 直接拼进 URL。
2. 构建并启动 PostgreSQL、迁移和 API：

   ```powershell
   docker compose up --build -d
   docker compose ps
   ```

3. 打开容器化 Operator Workbench：

   ```powershell
   Start-Process http://127.0.0.1:8000/operator-workbench/
   ```

4. 如需受控的虚构演示样例，显式执行：

   ```powershell
   docker compose --profile demo run --rm demo-seed
   ```

   seed 可重复执行，只补齐固定 demo 数据，不调用模型、不启动 Worker，也不创建外发任务。

### 本地源码调试

如需不经过 API 容器直接调试后端，保留以下方式：

```powershell
docker compose up -d postgres
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Worker 默认不随 Compose 启动。操作者显式启用后，它会处理 queued run：配置模型 Key 时调用 Provider；未配置 Key 时使用本地受限 fallback，并将 run 以 `llm_status=not_configured` 完成。

```powershell
docker compose --profile worker up -d worker
```

无论是否启动 Worker，系统都没有外部消息发送能力。

启用 Worker 会消耗 demo seed 中“草稿生成中”的 Casey 项并改变其状态；若需要保留该展示状态，请不要启动 `worker` profile。

## 日常操作

```powershell
docker compose logs -f postgres
docker compose logs -f api
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
docker compose up --build -d
```

执行前应再次确认目标不是需要保留的数据环境。

## 生产演进提醒

生产环境必须使用受管 PostgreSQL、受管 Secrets、备份恢复、监控和告警。当前 API 已独立容器运行，Worker 也有可选容器 profile；多 Worker 原子领取、渠道同步、镜像发布、监控和生产运行策略尚未实现。多 Worker 领取任务时应采用 PostgreSQL 的 `FOR UPDATE SKIP LOCKED` 或等价原子机制。
