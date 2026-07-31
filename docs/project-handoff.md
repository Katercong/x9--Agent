# 项目交接记录

> 最后更新：2026-07-31。目标规格见 [final-requirements.md](final-requirements.md)，当前实现范围见 [implementation-gap-review.md](implementation-gap-review.md)。本文只描述已验证的代码基线和接手顺序。

## 代码基线

- 已合并的 `main` 基线为 `11bad73 文档: 定义 Gmail 人工确认投递目标`，其中包含 V2/V3.2 默认配置、集合 SQL 审核队列、React 工作台、DNC/明确拒绝审核、人工导出交接、Dockerfile/Compose `migrate`/API/Worker profile、前端静态托管、受控 demo seed、RBAC Foundation，以及 PostgreSQL 原子多 Worker 领取与不可变事件留痕。
- 当前功能分支 `feat/manual-delivery-outbox-domain` 在该基线之上建设凭据无关的人工投递 Outbox：批准草稿会创建唯一不可变快照，原批准 reviewer/admin 可选择本人同部门账号完成第二次确认，原子预占账号日额度并仅进入本地 `queued`。该分支未接 OAuth、Gmail、X9 webhook 或 Delivery Worker。
- PostgreSQL 测试基础通过 `scripts/run-postgres-tests.ps1` 或 `scripts/run_postgres_tests.py` 创建随机 `x9_replychat_test_*` 数据库、执行 Alembic `head` 并在结束时删除。PowerShell 入口为每次执行生成独立 Compose 项目名和动态 loopback 端口，避免并行本机/worktree 测试互相关闭容器或删除 volume。没有运行器配置时直接执行 `pytest` 会失败，不会误用 `.env`、开发或演示库。
- 最近验证：后端 PostgreSQL 全量套件为 `181 passed`，覆盖完整/历史 Alembic 路径、部分唯一索引、不可变审计触发器、跨部门终态边界、API/Worker PostgreSQL fail-fast 与多 Worker 竞争/回收/旧结果丢弃，以及 Outbox 的快照、状态、DNC、二次确认、日额度和并发竞争。根测试入口和 PostgreSQL/Alembic 子进程均以 `X9_TEST_ISOLATED=1` 跳过 `.env`，不会继承本机 APP_ENV、RBAC 或 X9 设置。PowerShell 入口还覆盖 Docker 启动失败即中止，既不连接指定端口也不清理非本次成功启动的容器，并覆盖进程隔离的 Compose 项目与动态端口。GitHub Actions 使用一个 PostgreSQL 全量 job。前端 Vitest 基线为 `17 passed`，`npm run build` 已通过。本轮已用独立 Compose 项目构建镜像、迁移到 `5e6f7a8b9c0d`，并验证 API 健康检查和 `/operator-workbench/` 静态入口；默认仅启动 PostgreSQL、`migrate` 与 API，不启动 `worker` 或 `demo-seed`。此前 demo seed 已验证可在旧库已有同码部门目录时复用该目录项、补齐缺失本地映射而不覆盖数据。
- 本地数据库：Docker Compose 管理 PostgreSQL。默认服务为 PostgreSQL、一次性 `migrate` 和 API；`worker` 与 `demo-seed` 是显式 profile。`.env.example` 的 Docker 默认值只启用 loopback demo Fake Adapter，且未配置 X9 HMAC 密钥时传入有效空 JSON；生产必须改为 X9 签名断言和受管密钥。API、Worker 与自动化测试均只支持 PostgreSQL。

## 当前系统能力

```text
模拟入站回复
-> 确定性幂等入库与规则分类
-> queued Agent run
-> PostgreSQL 原子领取、LLM JSON/Pydantic 校验与 run/Worker 事件留痕
-> 人工审核队列 / 会话式 Operator Workbench
-> 人工编辑、批准或关闭；DNC 确认或驳回；模型失败可显式重试
-> 批准草稿生成不可变 Outbox 快照；原批准人可选本人账号二次确认
-> 本地 queued 投递单与额度/事件留痕；当前仍仅可复制或下载，不调用 Gmail
```

- 工作台地址为 `/operator-workbench/`。队列覆盖普通回复、模型失败、生成中、拒绝、DNC 待确认和已锁定待交接草稿；单项详情聚合达人、产品、资料、会话、事件、待办和全部 Agent run。
- 除 `/health` 外，业务 API 必须解析当前 Principal。Agent 本地 `AuthUser`、部门和成员关系是授权唯一权威；X9 仅能经短期签名断言提供稳定身份，Agent 不接收 `x9_session` Cookie、不读 X9 数据库。
- 工作台先读取 `/api/followup-agent/auth/me`，展示当前本地身份与部门角色，并按角色隐藏或禁用审核、DNC、重试和交接操作；服务端继续负责所有实际授权与审计主体。
- `departments` 是受保护的业务部门码目录：回填迁移会为历史业务码创建无成员关系的启用目录项，后续迁移会规范化目录与全部历史业务行的部门码。规范码只允许小写 ASCII 字母、数字和 `-`/`_` 分隔的 slug 段；API、授权主体、碰撞预检和最新前向迁移共用该规则。历史非 ASCII 或内部空白部门码会安全阻断迁移，而不会在运行时形成不可访问的授权范围。管理员只能创建从未使用的部门码；创建或迁移达人时，目标目录必须存在、启用且调用者在目标范围具备 `creator:manage`，防止管理员认领其他部门的既有业务数据，并保证已授予范围可读取历史数据。并发同名新部门以数据库唯一约束为最终裁决，接口会回滚失败事务并返回 `409`。
- DNC 是最高优先级安全边界：待确认或已确认后隐藏既有 AI 草稿和所有交接入口。DNC 确认永久阻断后续业务处理；驳回会显式新建审核 run，但不会发送消息。明确拒绝须由 reviewer/admin 显式确认：一次性审计后将达人置为 `dropped`、源回复置为 `reviewed`，并关闭同部门 open/pending 待办；不调用 LLM、不发送消息。
- AI 只能提供分类、上下文、草稿和建议；所有非终态推进须人工确认。复制/下载只写导出审计。批准草稿自动创建本地 Outbox 快照，二次确认只预占本地额度并进入 `queued`，不会调用真实渠道。当前没有 Gmail OAuth、Gmail SDK、IMAP、X9 webhook、Delivery Worker 或自动发送能力。
- 当前 Worker 以 PostgreSQL `FOR UPDATE SKIP LOCKED` 短事务领取；使用 120 秒 lease、claim token、当前 Worker ID 与条件回写。领取、完成、过期回收、旧结果丢弃均记录不可变最小事件；过期后标为 `failed/worker_lost`，只允许人工显式重试。手动重试的并发活跃 run 返回业务 `409`；无模型 Key 时仍使用本地受限 fallback 完成 queued run，配置 Key 后才调用 Provider。
- `demo-seed` 仅写入固定虚构样例，不调用模型或 Worker，不创建任何出站指令；基础 Docker 演示也不会启动 Worker。

## 代码定位

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 路由、审核读模型、明确拒绝/DNC 操作、Outbox 账号/二次确认/详情、导出审计和工作台静态挂载。 |
| `app/authorization.py` / `app/identity.py` | 角色能力策略、X9 HMAC 身份断言验证、demo Adapter 与当前 Principal。 |
| `app/rbac_bootstrap.py` | 显式 `--confirm` 的首管理员 bootstrap CLI。 |
| `app/services.py` / `app/worker.py` | 分类、上下文、PostgreSQL 原子领取、Worker ID、lease、条件回写、过期回收和事件留痕；Outbox 快照、状态转换、DNC 阻断、额度与二次确认领域规则。 |
| `app/models.py` / `alembic/versions/5e6f7a8b9c0d_add_manual_delivery_outbox_domain.py` | 无凭据账号目录、日额度、不可变投递请求/事件及其 PostgreSQL schema。 |
| `app/demo_seed.py` | 可重复、无外部副作用的工作台演示数据。 |
| `frontend/` | React + Vite + Ant Design + TanStack Query Operator Workbench。 |
| `Dockerfile` / `compose.yaml` | 前端构建、API 静态托管、迁移、PostgreSQL 和可选 Worker。 |
| `alembic/` / `tests/` | schema migration 与完整 PostgreSQL 自动化覆盖。 |
| `scripts/run_postgres_tests.py` / `scripts/run-postgres-tests.ps1` / `compose.postgres-test.yaml` | 随机测试库、隔离迁移、可靠清理与本地 PostgreSQL 测试容器入口。 |

## 近期已完成的关键提交

- `fa08293 feat: 切换默认V2提示词与DeepSeek V3.2模型 (#3)`
- `718e88b Feat/operator workbench export (#4)`
- `6bb394e feat: 完成工作台容器化演示交付 (#5)`
- `080f886 Feat/review queue sql optimization (#6)`
- `de227f5 构建 RBAC 授权数据与策略基础`
- `5f0f1f1 接入 X9 身份断言与权限主体`
- `5307480 限制业务读取的部门范围`
- `3e34752 保护业务写入并绑定审计主体`
- `3dcfdbb 完善管理员授权管理与审计`
- `a516319 Feat/rbac foundation (#7)`
- `79a83ef feat: 新增拒绝确认审计数据层`
- `caac27b feat: 支持人工确认明确拒绝`
- `fac0840 feat: 工作台支持确认明确拒绝`
- `79e6546 feat: 支持 PostgreSQL 原子领取任务`
- `6ea5c62 feat: 增加多 Worker 领取审计留痕`
- `19c667c test: 验证多 Worker 并发回收安全`
- `3a67753 test: 建立隔离 PostgreSQL 测试基础`
- `c7befb4 test: 补齐 PostgreSQL 核心集成套件`
- `5304c30 功能: 建立人工投递出站领域模型`
- `5d1f523 功能: 添加人工投递二次确认接口`
- `da4d2f2 修复: 强制人工投递二次确认不变量`
- `42294d6 测试: 覆盖人工投递账号额度并发竞争`
- `91cb66c 功能: 增加人工投递二次确认工作台`
- `6eaa2fb 修复: 完善投递状态时间展示`

## 接手时的优先顺序

1. 建设 Gmail OAuth、加密 Token 和企业 Workspace 域校验，以及 X9 creator/mailbox 映射、验签 webhook 与发送审计回写；Agent 不接收 X9 Session 或读取 X9 数据库。
2. 在上述边界完备后，建设独立 Gmail Delivery Worker：仅消费已二次确认的 `queued` 投递单，调用前再次检查 DNC；Gmail 明确失败才允许人工重新确认，未知结果绝不自动重试。
3. 基于已落库的 Worker/Outbox 事件补指标聚合、告警、备份恢复、受管多副本部署和容量验证。

每一步开始前都应重新阅读最终需求和实现缺口；若范围变化，先更新文档并获得 review，再进入代码实现。
