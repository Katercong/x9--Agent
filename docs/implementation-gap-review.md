# X9 ReplyChat Agent 阶段性实现复盘

> 对照：[最终需求规格](final-requirements.md)。本文记录事实状态，不等同于目标需求。本文截至 2026-07-29，覆盖已合并的工作台、容器化演示和审核队列 SQL 优化，以及当前 `feat/rbac-foundation` 分支中待 review 的 RBAC Foundation 六个阶段。

## 已实现

| 模块 | 当前能力 |
| --- | --- |
| 数据库与迁移 | Docker Compose PostgreSQL、`.env` 配置、Alembic `d7e8f9a0b1c2` 开发 head；SQLite 自动化测试兼容。Compose 默认编排 PostgreSQL、一次性 `migrate` 和 API。 |
| 数据完整性 | 外部消息 ID 非空与幂等；run 外键非空；审计关联禁止级联删除；每条回复最多一个活跃 run。 |
| 核心数据 | 达人、产品、参考资料版本、入站回复、Agent run、DNC、待办、事件、人工审核决定、草稿导出记录与历史模拟出站指令。 |
| AI 与 Worker | PostgreSQL 数据库队列、单 Worker 短事务领取、lease、claim token、过期回收和失败留痕；默认模型为 `reply_followup_v2` + `deepseek-ai/DeepSeek-V3.2`，传 `extra_body={"enable_thinking": false}`。未配置模型 Key 时 Worker 使用本地受限 fallback，仍完成 run 并进入人工审核。 |
| 人工审核 API | 审核队列支持普通回复、模型失败、生成中、拒绝、DNC、已批准草稿和 `reply_ready` 聚合；筛选、分类、排序、分页与关联预加载均由集合 SQL 完成，单次列表读取固定为总数与页面两条查询。`GET /review-items/{reply_id}` 返回上下文与完整 run 留痕。普通项可批准最终草稿或关闭；模型失败可人工重试，活跃 run 冲突返回 `409`。 |
| DNC 安全边界 | DNC 确认与驳回均需人工显式调用接口。待确认/已确认 DNC 优先阻断新 run、草稿、复制、下载、导出和既有普通待办；同一 DNC 只在源回复上显示为可操作队列项，历史会话标记为 `dnc_blocked`。 |
| 运营工作台 | React + Vite + TypeScript + Ant Design + TanStack Query 三栏工作台，提供会话上下文、AI 建议、草稿编辑、批准/关闭、DNC 确认或驳回、模型失败重试、复制和 `.txt` 下载审计。没有发送能力。 |
| RBAC Foundation | Agent 本地 `AuthUser`、`Department`、成员关系和追加式授权审计已落库；角色为 `operator`、`reviewer`、`admin`。除 `/health` 外的业务 API 均解析 Principal，并按部门范围执行 `401`、`403` 或跨部门 `404`。历史业务部门码已回填为无授权目录项并规范化目录与历史业务行，禁止管理员认领已使用的部门码且保持已授权历史数据可访问；同名新部门的并发唯一约束冲突会回滚并转换为 `409`。部门码使用 ASCII slug，迁移预检拒绝历史非法值，避免依赖 SQLite/PostgreSQL 不一致的 Unicode 大小写。本轮待 review P2 将已发布 revision 绑定到冻结 V1 规则，防止未来应用 helper 改动重写历史迁移语义。 |
| 身份适配 | Agent 不接收 X9 Cookie、不读 X9 数据库。生产预留短期 HMAC 身份断言；本地 demo/test 才允许 Fake Adapter。`/auth/me` 仅返回 Agent 本地显示身份、角色和能力。 |
| 管理员授权 | 管理员只能在自身授权部门内创建/软停用用户、部门和成员关系；每次变更追加 `authorization_audit_events`，没有物理删除接口。 |
| 容器化演示 | 提供多阶段镜像、API 静态托管 `/operator-workbench/`、`worker` profile 和显式 `demo-seed` profile。Compose 的 loopback demo 使用虚构本地 operator/reviewer/admin；未配置 X9 HMAC 密钥时传入有效空 JSON 并继续使用 demo Adapter；种子幂等、不调用模型、不创建出站指令。 |
| 验证 | Python 全量测试为 `132 passed`；前端 Vitest 为 `10 passed`，并已验证前端构建。已使用独立 Compose 项目完成 Docker 迁移、健康检查、静态资源、demo 身份、六类队列与重复 demo seed（第二次新增 `0` 条）的完整 RBAC 演练；本轮另验证隔离 PostgreSQL 旧库从 `d7e8f9a0b1c2` 升级时，当前 head `2b3c4d5e6f7a` 会原子地拒绝带 tab/换行的非 ASCII 大写历史部门码。仅有既有 FastAPI `on_event` 弃用警告和 Vite 既有的大 bundle 提示。 |

## 已实现但与目标仍有差距

| 项目 | 当前状态 | 下一步 |
| --- | --- | --- |
| 企业身份接入 | 授权目录、角色、部门隔离、管理员审计与 HMAC Adapter 契约已完成；真实 X9 尚未提供可调用的签名断言出口。 | 由 X9 独立交付 Session 验证后的短期签名断言和受管密钥，再进行联调；Agent 仍不接收 `x9_session`。 |
| 终态审核 | DNC 已支持确认/驳回并留痕；明确拒绝仍是只读终态记录，尚无人工确认 `dropped` 的状态转换。 | 在 RBAC 设计完成后补齐拒绝确认、DNC 解除和退信复核的状态机与审计。 |
| 多 Worker 与观测 | 当前 Worker 仍按单 Worker 可靠性设计；Compose 仅提供可选单 Worker profile。 | 使用 PostgreSQL 原子并发领取，补指标、告警、容量与故障恢复验证。 |
| 容器化交付 | 本地演示镜像、迁移、健康检查和 seed 已具备；尚不是受管生产部署。 | 补受管 Secrets、备份恢复、日志/监控、镜像发布和生产运行策略。 |
| 审计治理 | 已有 run、人工决定、DNC、导出内容快照和管理员授权变更审计。 | 补 24 个月保留/清理策略与生产审计检索治理。 |

## 未实现需求

- 真实 X9 身份提供方的签名断言出口、受管密钥和联调；本地 Adapter 契约不等于生产认证集成。
- 外接渠道待选。选定后才可实现适配器、认证、初始回填、增量同步、游标、重试、回补和契约测试。
- 真实消息解析、稳定消息/会话标识保存、待匹配队列及人工关联/建档。
- 站内通知、负责人、优先级和到期日。
- 拒绝确认 `dropped`、DNC 解除和退信复核的受 RBAC 保护写接口。
- 生产级多 Worker、受管 Secrets、备份恢复、监控告警和端到端容量测试。

## 实施约束

外接渠道发送能力不在未实现清单中：最终需求明确禁止系统自动发送。当前和后续功能只能实现人工确认后的复制或导出交接；禁用的发送占位与 `delivery-capability` 只读接口均不得创建发送请求、任务或记录。
