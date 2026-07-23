# 项目交接记录

> 最后更新：2026-07-23。目标规格见 [final-requirements.md](final-requirements.md)，当前实现范围见 [implementation-gap-review.md](implementation-gap-review.md)。本文只描述已验证的代码基线和接手顺序。

## 代码基线

- 远端 `main` 当前基线为 `718e88b Feat/operator workbench export (#4)`，包含 V2/V3.2 默认配置、人工审核读模型、React 工作台、DNC 审核动作和人工导出交接。
- 当前功能分支为 `feat/demo-delivery`，已推送的 `767aa98 feat: 完成工作台容器化演示交付` 增加 Dockerfile、Compose `migrate`/API/Worker profile、前端静态托管和受控 demo seed；本分支等待 PR review 与合并。
- 最近验证：`python -m pytest -q` 为 `85 passed`，前端 `npm run test` 为 `8 passed`；Docker 已验证镜像构建、Alembic `ab12cd34ef56 (head)`、`/health`、`/operator-workbench/` 静态资源和重复 seed 幂等性。仅有 FastAPI `on_event` 既有弃用警告。
- 本地数据库：Docker Compose 管理 PostgreSQL。默认服务为 PostgreSQL、一次性 `migrate` 和 API；`worker` 与 `demo-seed` 是显式 profile。SQLite 只用于自动化测试和可丢弃的本地 MVP 数据。

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
- DNC 是最高优先级安全边界：待确认或已确认后隐藏既有 AI 草稿和所有交接入口。DNC 确认永久阻断后续业务处理；驳回会显式新建审核 run，但不会发送消息。明确拒绝仍是只读终态，尚未实现确认 `dropped`。
- AI 只能提供分类、上下文、草稿和建议；所有非终态推进须人工确认。复制/下载只写导出审计，不会调用真实渠道。没有 Gmail、IMAP、X9 或自动发送能力。
- 当前 Worker 使用短事务领取、120 秒 lease、claim token 条件回写和过期回收。手动重试的并发活跃 run 会返回业务 `409`；无模型 Key 时仍使用本地受限 fallback 完成 queued run，配置 Key 后才调用 Provider。
- `demo-seed` 仅写入固定虚构样例，不调用模型或 Worker，不创建任何出站指令；基础 Docker 演示也不会启动 Worker。

## 代码定位

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 路由、审核读模型、DNC 操作、导出审计和工作台静态挂载。 |
| `app/services.py` / `app/worker.py` | 分类、上下文、数据库队列、lease 和条件回写。 |
| `app/demo_seed.py` | 可重复、无外部副作用的工作台演示数据。 |
| `frontend/` | React + Vite + Ant Design + TanStack Query Operator Workbench。 |
| `Dockerfile` / `compose.yaml` | 前端构建、API 静态托管、迁移、PostgreSQL 和可选 Worker。 |
| `alembic/` / `tests/` | schema migration 与后端回归覆盖。 |

## 近期已完成的关键提交

- `fa08293 feat: 切换默认V2提示词与DeepSeek V3.2模型 (#3)`
- `718e88b Feat/operator workbench export (#4)`
- `767aa98 feat: 完成工作台容器化演示交付`

## 接手时的优先顺序

1. 为审核队列实施 SQL 级筛选、排序、分页和关联预加载，消除应用层分页与 N+1 查询。
2. 选定身份提供方后建设用户、部门成员关系与 RBAC；随后补齐拒绝确认、DNC 解除和退信复核的受权状态机。
3. 使用 PostgreSQL 原子并发领取完善多 Worker，补监控、告警、备份恢复和容量验证。
4. 在渠道选型和详细规格明确后，才建设渠道适配、同步、待匹配队列和人工交接；系统仍不得自动发送。

每一步开始前都应重新阅读最终需求和实现缺口；若范围变化，先更新文档并获得 review，再进入代码实现。
