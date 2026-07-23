# X9 ReplyChat Agent 阶段性实现复盘

> 对照：[最终需求规格](final-requirements.md)。本文记录事实状态，不等同于目标需求。本文截至 2026-07-23，覆盖 `main` 已合并的工作台核心，以及当前 `feat/demo-delivery` 分支中待合并的容器化演示交付。

## 已实现

| 模块 | 当前能力 |
| --- | --- |
| 数据库与迁移 | Docker Compose PostgreSQL、`.env` 配置、Alembic `ab12cd34ef56` head；SQLite 自动化测试兼容。Compose 默认编排 PostgreSQL、一次性 `migrate` 和 API。 |
| 数据完整性 | 外部消息 ID 非空与幂等；run 外键非空；审计关联禁止级联删除；每条回复最多一个活跃 run。 |
| 核心数据 | 达人、产品、参考资料版本、入站回复、Agent run、DNC、待办、事件、人工审核决定、草稿导出记录与历史模拟出站指令。 |
| AI 与 Worker | PostgreSQL 数据库队列、单 Worker 短事务领取、lease、claim token、过期回收和失败留痕；默认模型为 `reply_followup_v2` + `deepseek-ai/DeepSeek-V3.2`，传 `extra_body={"enable_thinking": false}`。 |
| 人工审核 API | 审核队列支持普通回复、模型失败、生成中、拒绝、DNC、已批准草稿和 `reply_ready` 聚合；`GET /review-items/{reply_id}` 返回上下文与完整 run 留痕。普通项可批准最终草稿或关闭；模型失败可人工重试，活跃 run 冲突返回 `409`。 |
| DNC 安全边界 | DNC 确认与驳回均需人工显式调用接口。待确认/已确认 DNC 优先阻断新 run、草稿、复制、下载、导出和既有普通待办；同一 DNC 只在源回复上显示为可操作队列项，历史会话标记为 `dnc_blocked`。 |
| 运营工作台 | React + Vite + TypeScript + Ant Design + TanStack Query 三栏工作台，提供会话上下文、AI 建议、草稿编辑、批准/关闭、DNC 确认或驳回、模型失败重试、复制和 `.txt` 下载审计。没有发送能力。 |
| 容器化演示 | 当前 `feat/demo-delivery` 提供多阶段镜像、API 静态托管 `/operator-workbench/`、`worker` profile 和显式 `demo-seed` profile。种子使用固定虚构数据且幂等，不调用模型、不创建出站指令。 |
| 验证 | Python 全量测试为 `82 passed`，前端 Vitest 为 `8 passed`；已验证 Docker 镜像构建、迁移、API 健康检查、静态资源和重复 demo seed。仅有既有 FastAPI `on_event` 弃用警告。 |

## 已实现但与目标仍有差距

| 项目 | 当前状态 | 下一步 |
| --- | --- | --- |
| 人工审核权限 | 无登录模式下 `actor_id=demo_operator` 仅用于审计；没有用户、部门成员关系或 RBAC。 | 选定身份提供方后建模运营、审核、管理员及跨部门隔离。 |
| 终态审核 | DNC 已支持确认/驳回并留痕；明确拒绝仍是只读终态记录，尚无人工确认 `dropped` 的状态转换。 | 在 RBAC 设计完成后补齐拒绝确认、DNC 解除和退信复核的状态机与审计。 |
| 队列性能 | 审核队列在应用层做分页，并逐项读取 run、DNC 与审核决定。 | 将筛选、排序、分页和关联预加载下推到 SQL，消除 N+1 查询。 |
| 多 Worker 与观测 | 当前 Worker 仍按单 Worker 可靠性设计；Compose 仅提供可选单 Worker profile。 | 使用 PostgreSQL 原子并发领取，补指标、告警、容量与故障恢复验证。 |
| 容器化交付 | 本地演示镜像、迁移、健康检查和 seed 已具备；尚不是受管生产部署。 | 补受管 Secrets、备份恢复、日志/监控、镜像发布和生产运行策略。 |
| 审计治理 | 已有 run、人工决定、DNC 事件与导出内容快照。 | 补管理员操作审计、权限上下文、24 个月保留/清理策略。 |

## 未实现需求

- 企业身份提供方待定的认证集成、运营/审核/管理员角色和跨部门隔离。
- 外接渠道待选。选定后才可实现适配器、认证、初始回填、增量同步、游标、重试、回补和契约测试。
- 真实消息解析、稳定消息/会话标识保存、待匹配队列及人工关联/建档。
- 站内通知、负责人、优先级和到期日，以及队列的 SQL 级扩展性优化。
- 拒绝确认 `dropped`、DNC 解除和退信复核的受 RBAC 保护写接口。
- 生产级多 Worker、受管 Secrets、备份恢复、监控告警和端到端容量测试。

## 实施约束

外接渠道发送能力不在未实现清单中：最终需求明确禁止系统自动发送。当前和后续功能只能实现人工确认后的复制或导出交接；禁用的发送占位与 `delivery-capability` 只读接口均不得创建发送请求、任务或记录。
