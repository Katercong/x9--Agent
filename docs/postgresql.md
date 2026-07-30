# PostgreSQL 本地部署、容器化工作台与迁移

> 本文说明当前仓库的本地 PostgreSQL 和容器化工作台运行方式。生产目标和边界以 [最终需求规格](final-requirements.md) 为准；当前 Compose 用于本地演示，不等同于受管生产部署。

## 数据持久化与安全边界

PostgreSQL 由 Docker Compose 管理，数据保存在 Docker 命名卷 `x9-replychat_postgres_data`。默认 Compose 会启动 PostgreSQL、一次性 Alembic `migrate` 和 FastAPI `api`；`worker` 和 `demo-seed` 仅在显式 profile 中运行。删除容器不会删除数据卷；`docker compose down --volumes` 会清空本地数据库，只能用于确认可丢弃的数据。

服务只绑定 `127.0.0.1`，不会直接暴露到局域网。`.env` 已被 Git 忽略，真实密码、数据库 URL 和模型密钥不得写入代码或文档。

`.env.example` 的 `APP_ENV=demo` 与 `RBAC_AUTH_MODE=demo` 仅服务于本机 loopback 演示：API 使用虚构本地身份，不接收 X9 Cookie。未配置 X9 HMAC 密钥时，Compose 会向容器传入有效空 JSON；因为 demo Adapter 不读取该密钥，工作台身份仍可正常解析。受管部署必须显式配置 X9 的短期签名断言 Adapter 与受管密钥；不能把 demo 配置带入生产。

## 首次启动

1. 从 `.env.example` 创建本机 `.env`，设置新的原始 `POSTGRES_PASSWORD`，以及两条已编码连接 URL：
   `DATABASE_URL` 供本机 Uvicorn/Alembic 使用，主机为 `127.0.0.1`；`DATABASE_URL_CONTAINER` 供 Compose 的 migrate、API、Worker 和 demo seed 使用，主机为 `postgres`。
   若用户名或密码含 `@`、`:`、`/` 等 URL 保留字符，必须在两条 URL 中分别进行百分号编码；不要把原始 `POSTGRES_PASSWORD` 直接拼进 URL。`.env` 中保留标准 `%xx` 编码即可，Alembic 会在内部安全处理 ConfigParser 的转义。
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

   seed 可重复执行，只补齐固定 demo 数据，以及虚构 `demo_operator`、`demo_reviewer`、`demo_admin` 在 `demo_operations` 的成员关系；不调用模型、不启动 Worker，也不创建外发任务。

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
python -m pytest -q -m "not postgres_integration"
```

所有 schema 修改必须先新增 Alembic migration，再执行 `alembic upgrade head`。应用启动不会自动建表或修改 PostgreSQL schema。

## PostgreSQL 专用测试

SQLite 快速回归与真实 PostgreSQL 集成测试刻意分开。前者不依赖 Docker；后者覆盖高风险的迁移、部分唯一约束、审计限制、跨部门终态边界和多 Worker `SKIP LOCKED` 领取，不会双跑全部 API 用例。

```powershell
python -m pytest -q -m "not postgres_integration"
.\scripts\run-postgres-tests.ps1
```

`run-postgres-tests.ps1` 只启动 `compose.postgres-test.yaml` 中的专用 PostgreSQL 服务（默认 loopback 端口 `55432`），再调用 `scripts/run_postgres_tests.py`。运行器仅接受该服务的 `postgres` 控制库 URL，创建随机 `x9_replychat_test_*` 数据库、先执行 `alembic upgrade head`，再将生成的数据库 URL 传给带 `postgres_integration` marker 的测试。无论成功或失败，都会断开连接并删除本次数据库；PowerShell 包装器还会删除测试容器、网络和 volume。

该过程不读取 `.env`、不使用开发/演示数据库、不启动 API/Worker、不调用模型，也不创建任何出站指令。请勿直接运行 `pytest -m postgres_integration`：没有专用运行器时测试会明确失败，避免误指向非测试数据库后静默通过。GitHub Actions 使用同一 Python 运行器配合独立 `postgres:16-alpine` service 和公开的测试专用凭据。

## 当前迁移的完整性约束

当前初始迁移已与 ORM 对齐，并在 PostgreSQL 与 SQLite 验证以下约束：

- `inbound_replies.external_message_id` 必填；重复稳定外部消息 ID 被拒绝。
- `agent_followup_runs.creator_id`、`inbound_reply_id` 必填且受外键约束；孤儿 run 被拒绝。
- 同一 `inbound_reply_id` 在 `execution_status IN ('queued', 'running')` 时最多一条 run。
- DNC、入站回复、人工待办、模拟出站指令等审计关联不使用 `ON DELETE CASCADE`；删除已有审计关联的 reply 或 creator 会被拒绝。
- `auth_users` 的 `identity_source + external_subject` 唯一；成员关系的用户/部门组合唯一，角色只允许 `operator`、`reviewer`、`admin`。
- 授权目录和 `authorization_audit_events` 的全部外键使用 `RESTRICT`；撤权只能通过软停用，不能删除审计链路。

由于初始 migration 已存在，环境需要重新初始化时只可对可丢弃的本地库执行：

```powershell
docker compose down --volumes
docker compose up --build -d
```

执行前应再次确认目标不是需要保留的数据环境。

## 生产演进提醒

生产环境必须使用受管 PostgreSQL、受管 Secrets、备份恢复、监控和告警。当前 API 已独立容器运行，Worker 也有可选容器 profile；多 Worker 已通过 PostgreSQL `FOR UPDATE SKIP LOCKED` 实现事务级原子领取，并由 SQLite 快速回归、真实 PostgreSQL 核心套件和 CI 分别验证。渠道同步、镜像发布、监控告警、受管多副本部署和生产运行策略仍未实现。
