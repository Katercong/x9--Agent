# Operator Workbench 容器化演示指南

## 前置条件

- 已安装 Docker Desktop，并确保 Docker Engine 已启动。
- 从 `.env.example` 创建本机 `.env`，填写 PostgreSQL 变量。不要提交 `.env`，也不需要为基础演示填写模型 Key。

## 启动与载入样例

在仓库根目录执行：

```powershell
docker compose up --build -d
docker compose --profile demo run --rm demo-seed
```

`migrate` 会先执行 Alembic，`api` 健康检查通过后提供工作台。`demo-seed` 仅在显式运行时补齐固定的虚构数据；可重复执行，不会删除或覆盖操作者在本地库中的后续操作。

打开 [http://127.0.0.1:8000/operator-workbench/](http://127.0.0.1:8000/operator-workbench/)。若修改 `API_PORT`，请使用对应端口。

## 建议演示路径

1. **人工回复草稿**：打开“Alex Demo”，查看历史上下文、AI 建议和可编辑草稿；批准后草稿会锁定为待人工交接。
2. **模型生成失败**：打开“Blair Demo”，查看校验失败留痕；可从空白草稿人工起草，或明确启用 Worker 后重试。Worker 有模型 Key 时调用 Provider；无 Key 时会生成受限本地 fallback 草稿。
3. **草稿生成中**：打开“Casey Demo”，查看数据库队列中的待处理 run。基础演示不会启动 Worker；一旦显式启动，Casey 会被处理并离开“草稿生成中”。
4. **明确拒绝**：打开“Drew Demo”，确认终态项只能查看，不能起草、批准、复制或下载。
5. **DNC 待确认**：打开“Evan Demo”，确认永久停联或驳回后重新进入人工审核；在待确认期间不会展示可交接草稿。
6. **已锁定待交接草稿**：打开“Fran Demo”，复制或下载批准后的草稿；动作会写入导出审计快照。

## 安全边界

- 所有达人、邮件地址、产品和消息内容均为虚构演示数据。
- 复制或下载只是人工交接，不会发送邮件、创建外发任务或调用任何真实渠道。
- `worker` 是可选 profile：`docker compose --profile worker up -d worker`。它只在操作者显式启用后处理 queued run：配置模型 Key 时调用 Provider；未配置 Key 时生成本地受限 fallback，并以 `llm_status=not_configured` 成功进入人工审核。两种路径都会改变 Casey 的“生成中”状态，但都不会发送消息或调用外部渠道。

## 停止与清理

```powershell
docker compose down
```

如需删除本地 PostgreSQL 演示数据，可由操作者明确执行 `docker compose down -v`。该命令会删除 Docker volume，不能恢复。
