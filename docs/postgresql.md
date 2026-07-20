# PostgreSQL 本地部署与迁移

本项目的 PostgreSQL 由 Docker Compose 管理，数据保存在 Docker 命名卷
`x9-replychat_postgres_data` 中。删除容器不会删除数据卷；只有显式执行
`docker compose down --volumes` 才会清空本地数据库，不能对需要保留的数据执行该命令。

## 首次启动

1. 将 `.env.example` 中的 PostgreSQL 变量复制到本机 `.env`。`POSTGRES_PASSWORD`
   必须使用新的本地密码，且不要提交 `.env`。若密码包含 `@`、`:`、`/` 等 URL
   保留字符，`DATABASE_URL` 里的密码部分必须进行百分号编码。
2. 启动并等待数据库就绪：

   ```powershell
   docker compose up -d postgres
   docker compose ps
   ```

3. 安装依赖并将 schema 迁移到当前版本：

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
```

PostgreSQL 仅绑定 `127.0.0.1`，不会直接暴露到局域网。将来 API 也容器化后，
应移除宿主机端口映射，并让 API 通过 Docker 内部网络连接 `postgres:5432`。

## 职责边界

- `alembic upgrade head` 是唯一允许生产 schema 变更的入口；应用启动不会自动建表。
- SQLite 仅保留给现有自动化测试和可丢弃的本地 MVP 数据。
- 当前 SQLite 的历史业务数据不自动迁移。导入前需要先备份、验证行数/约束并安排回滚，
  这会在独立的数据迁移模块中完成。
