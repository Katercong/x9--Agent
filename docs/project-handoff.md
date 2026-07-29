# 项目交接记录

> 最后更新：2026-07-29。目标规格见 [final-requirements.md](final-requirements.md)，当前实现范围见 [implementation-gap-review.md](implementation-gap-review.md)。本文只描述已验证的代码基线和接手顺序。

## 代码基线

- 远端 `main` 当前基线为 `080f886 Feat/review queue sql optimization (#6)`，已包含 V2/V3.2 默认配置、集合 SQL 审核队列、React 工作台、DNC 审核动作、人工导出交接，以及 Dockerfile、Compose `migrate`/API/Worker profile、前端静态托管和受控 demo seed。
- 当前功能分支为 `feat/rbac-foundation`：已推送 `de227f5`（授权目录与策略）、`5f0f1f1`（身份 Adapter）、`5307480`（读范围）、`3e34752`（写范围）和 `3dcfdbb`（管理员授权审计）；第六阶段等待 review 后提交。
- 最近验证：后端相关测试为 `120 passed`，前端 `npm run test -- --run` 为 `10 passed`，`npm run build` 通过；仅有 FastAPI `on_event` 既有弃用警告和 Vite 既有的大 bundle 提示。RBAC Docker 全链路演练尚未完成：本轮本机 Docker Engine 不可用。
- 本地数据库：Docker Compose 管理 PostgreSQL。默认服务为 PostgreSQL、一次性 `migrate` 和 API；`worker` 与 `demo-seed` 是显式 profile。`.env.example` 的 Docker 默认值只启用 loopback demo Fake Adapter；生产必须改为 X9 签名断言。SQLite 只用于自动化测试和可丢弃的本地 MVP 数据。

## 当前系统能力

```text
模拟入站回复
-> 确定性幂等入库与规则分类
-> queued Agent run
-> Worker 领取、LLM JSON/Pydantic 校验与 run 留痕
-> 人工审核队列 / 会话式 Operator Workbench
-> 人工编辑、批准或关闭；DNC 确认或驳回；模型失败可显式重试
-> 已批准草稿仅可复制或下载，并记录导出快照
```

- 工作台地址为 `/operator-workbench/`。队列覆盖普通回复、模型失败、生成中、拒绝、DNC 待确认和已锁定待交接草稿；单项详情聚合达人、产品、资料、会话、事件、待办和全部 Agent run。
- 除 `/health` 外，业务 API 必须解析当前 Principal。Agent 本地 `AuthUser`、部门和成员关系是授权唯一权威；X9 仅能经短期签名断言提供稳定身份，Agent 不接收 `x9_session` Cookie、不读 X9 数据库。
- 工作台先读取 `/api/followup-agent/auth/me`，展示当前本地身份与部门角色，并按角色隐藏或禁用审核、DNC、重试和交接操作；服务端继续负责所有实际授权与审计主体。
- DNC 是最高优先级安全边界：待确认或已确认后隐藏既有 AI 草稿和所有交接入口。DNC 确认永久阻断后续业务处理；驳回会显式新建审核 run，但不会发送消息。明确拒绝仍是只读终态，尚未实现确认 `dropped`。
- AI 只能提供分类、上下文、草稿和建议；所有非终态推进须人工确认。复制/下载只写导出审计，不会调用真实渠道。没有 Gmail、IMAP、X9 或自动发送能力。
- 当前 Worker 使用短事务领取、120 秒 lease、claim token 条件回写和过期回收。手动重试的并发活跃 run 会返回业务 `409`；无模型 Key 时仍使用本地受限 fallback 完成 queued run，配置 Key 后才调用 Provider。
- `demo-seed` 仅写入固定虚构样例，不调用模型或 Worker，不创建任何出站指令；基础 Docker 演示也不会启动 Worker。

## 代码定位

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 路由、审核读模型、DNC 操作、导出审计和工作台静态挂载。 |
| `app/authorization.py` / `app/identity.py` | 角色能力策略、X9 HMAC 身份断言验证、demo Adapter 与当前 Principal。 |
| `app/rbac_bootstrap.py` | 显式 `--confirm` 的首管理员 bootstrap CLI。 |
| `app/services.py` / `app/worker.py` | 分类、上下文、数据库队列、lease 和条件回写。 |
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

## 接手时的优先顺序

1. Review 并完成 `feat/rbac-foundation` 第六阶段的 Docker 演练；确认后合并、删除本地与远端功能分支。
2. 由 X9 独立交付 Session 验证后的短期签名断言出口和受管密钥，再进行真实身份联调；Agent 不接收 X9 Session。
3. 补齐拒绝确认、DNC 解除和退信复核的受 RBAC 保护状态机。
4. 使用 PostgreSQL 原子并发领取完善多 Worker，补监控、告警、备份恢复和容量验证；渠道选型和详细规格明确后才可建设适配与同步，系统仍不得自动发送。

每一步开始前都应重新阅读最终需求和实现缺口；若范围变化，先更新文档并获得 review，再进入代码实现。
