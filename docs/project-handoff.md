# 项目交接记录

> 最后更新：2026-07-29。目标规格见 [final-requirements.md](final-requirements.md)，当前实现范围见 [implementation-gap-review.md](implementation-gap-review.md)。本文只描述已验证的代码基线和接手顺序。

## 代码基线

- 已合并的 `main` 基线为 `fe39772 feat: 人工确认明确拒绝并完成审计闭环 (#8)`，其中包含 V2/V3.2 默认配置、集合 SQL 审核队列、React 工作台、DNC/明确拒绝审核、人工导出交接，以及 Dockerfile、Compose `migrate`/API/Worker profile、前端静态托管、受控 demo seed 和 RBAC Foundation。
- 当前 `feat/postgres-multi-worker-claim` 分支等待最终 review：`79e6546` 增加 PostgreSQL 原子领取，`6ea5c62` 增加 Worker 身份和不可变事件留痕，`19c667c` 增加并发回收与显式 PostgreSQL 集成测试。其开发 migration head 为 `4d5e6f7a8b9c`；在最终 review 与合并前不要将这些实现视为 `main` 已有能力。
- 最近验证：当前分支默认后端全量测试为 `147 passed, 1 skipped`（显式 PostgreSQL 集成测试默认跳过）；前端 Vitest 基线为 `12 passed`，`npm run build` 已通过。已用隔离 Compose 项目完成迁移到 `4d5e6f7a8b9c`、API 健康检查、`/operator-workbench/` 静态资源、demo 身份、六类队列、成功确认拒绝，以及两事务 `SKIP LOCKED` 领取、单任务防重复领取、并发过期回收单次留痕和旧 Worker 结果丢弃；模拟出站指令数保持 `0`。demo seed 也验证可在旧库已有同码部门目录时复用该目录项、补齐缺失本地映射而不覆盖数据。
- 本地数据库：Docker Compose 管理 PostgreSQL。默认服务为 PostgreSQL、一次性 `migrate` 和 API；`worker` 与 `demo-seed` 是显式 profile。`.env.example` 的 Docker 默认值只启用 loopback demo Fake Adapter，且未配置 X9 HMAC 密钥时传入有效空 JSON；生产必须改为 X9 签名断言和受管密钥。SQLite 只用于自动化测试和可丢弃的本地 MVP 数据。

## 当前系统能力

```text
模拟入站回复
-> 确定性幂等入库与规则分类
-> queued Agent run
-> PostgreSQL 原子领取、LLM JSON/Pydantic 校验与 run/Worker 事件留痕
-> 人工审核队列 / 会话式 Operator Workbench
-> 人工编辑、批准或关闭；DNC 确认或驳回；模型失败可显式重试
-> 已批准草稿仅可复制或下载，并记录导出快照
```

- 工作台地址为 `/operator-workbench/`。队列覆盖普通回复、模型失败、生成中、拒绝、DNC 待确认和已锁定待交接草稿；单项详情聚合达人、产品、资料、会话、事件、待办和全部 Agent run。
- 除 `/health` 外，业务 API 必须解析当前 Principal。Agent 本地 `AuthUser`、部门和成员关系是授权唯一权威；X9 仅能经短期签名断言提供稳定身份，Agent 不接收 `x9_session` Cookie、不读 X9 数据库。
- 工作台先读取 `/api/followup-agent/auth/me`，展示当前本地身份与部门角色，并按角色隐藏或禁用审核、DNC、重试和交接操作；服务端继续负责所有实际授权与审计主体。
- `departments` 是受保护的业务部门码目录：回填迁移会为历史业务码创建无成员关系的启用目录项，后续迁移会规范化目录与全部历史业务行的部门码。规范码只允许小写 ASCII 字母、数字和 `-`/`_` 分隔的 slug 段；API、授权主体、碰撞预检和最新前向迁移共用该规则。历史非 ASCII 或内部空白部门码会安全阻断迁移，而不会在运行时形成不可访问的授权范围。管理员只能创建从未使用的部门码；创建或迁移达人时，目标目录必须存在、启用且调用者在目标范围具备 `creator:manage`，防止管理员认领其他部门的既有业务数据，并保证已授予范围可读取历史数据。并发同名新部门以数据库唯一约束为最终裁决，接口会回滚失败事务并返回 `409`。
- DNC 是最高优先级安全边界：待确认或已确认后隐藏既有 AI 草稿和所有交接入口。DNC 确认永久阻断后续业务处理；驳回会显式新建审核 run，但不会发送消息。明确拒绝须由 reviewer/admin 显式确认：一次性审计后将达人置为 `dropped`、源回复置为 `reviewed`，并关闭同部门 open/pending 待办；不调用 LLM、不发送消息。
- AI 只能提供分类、上下文、草稿和建议；所有非终态推进须人工确认。复制/下载只写导出审计，不会调用真实渠道。没有 Gmail、IMAP、X9 或自动发送能力。
- 当前 Worker 在 PostgreSQL 以 `FOR UPDATE SKIP LOCKED` 短事务领取，在 SQLite 使用条件更新回退；使用 120 秒 lease、claim token、当前 Worker ID 与条件回写。领取、完成、过期回收、旧结果丢弃均记录不可变最小事件；过期后标为 `failed/worker_lost`，只允许人工显式重试。手动重试的并发活跃 run 返回业务 `409`；无模型 Key 时仍使用本地受限 fallback 完成 queued run，配置 Key 后才调用 Provider。
- `demo-seed` 仅写入固定虚构样例，不调用模型或 Worker，不创建任何出站指令；基础 Docker 演示也不会启动 Worker。

## 代码定位

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 路由、审核读模型、明确拒绝/DNC 操作、导出审计和工作台静态挂载。 |
| `app/authorization.py` / `app/identity.py` | 角色能力策略、X9 HMAC 身份断言验证、demo Adapter 与当前 Principal。 |
| `app/rbac_bootstrap.py` | 显式 `--confirm` 的首管理员 bootstrap CLI。 |
| `app/services.py` / `app/worker.py` | 分类、上下文、PostgreSQL 原子领取、Worker ID、lease、条件回写、过期回收和事件留痕。 |
| `app/demo_seed.py` | 可重复、无外部副作用的工作台演示数据。 |
| `frontend/` | React + Vite + Ant Design + TanStack Query Operator Workbench。 |
| `Dockerfile` / `compose.yaml` | 前端构建、API 静态托管、迁移、PostgreSQL 和可选 Worker。 |
| `alembic/` / `tests/` | schema migration 与后端回归覆盖。 |

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

## 接手时的优先顺序

1. 由 X9 独立交付 Session 验证后的短期签名断言出口和受管密钥，再基于已合并的 RBAC Foundation 进行真实身份联调；Agent 不接收 X9 Session。
2. 基于已落库的 Worker 事件补指标聚合、告警、备份恢复、受管多副本部署和容量验证；渠道选型和详细规格明确后才可建设适配与同步，系统仍不得自动发送。

每一步开始前都应重新阅读最终需求和实现缺口；若范围变化，先更新文档并获得 review，再进入代码实现。
