# RBAC Foundation 与 X9 身份适配计划

> 当前进度（2026-07-29）：PR1 至 PR6、P1 历史部门码修复与 P2 并发部门创建 `409` 修复均已完成并推送；已完成独立 Docker Compose 的迁移、健康检查、工作台、demo 身份、六类队列和重复 seed 幂等性演练。本轮 P1 边界空白字符修复在当前工作区等待 review：API 与前向迁移共用部门码规范化规则，制表符/换行包裹的历史部门码也会成为可授权、可访问的规范码。本机 demo 的未配置 X9 密钥使用有效空 JSON 默认值，不会影响 `demo` Adapter；真实 X9 签名断言出口仍是外部前置条件。

## 目标与固定决策

ReplyChat Agent 建立按部门隔离、可审计的 `operator`、`reviewer`、`admin` 权限体系，并保留安全接入 X9 身份的边界。

- X9 只提供稳定且已认证的身份；Agent 本地用户、部门成员关系和角色是授权唯一权威。
- Agent 不读取 X9 数据库、不接收或转发 `x9_session` Cookie，不复制 X9 业务、Gmail 或外联代码。
- 除 `/health` 外，所有 `/api/followup-agent/*` 业务接口最终均要求当前 Principal。
- `departments` 是全部业务 `department_code` 的受保护目录，而不是可任意认领的标签表；既有业务码必须先由迁移回填为未授予成员关系的启用目录项。规范码统一为小写，并移除边界处的 ASCII 空格、制表符、换行、回车、垂直制表符和换页符；内部字符保持不变。
- 已授权 admin 仅能创建从未出现在目录或业务数据中的全新部门；创建成功后才获得该新部门的 admin。创建或迁移达人时，目标部门必须存在、启用且具备目标范围的 `creator:manage`。
- 不新增真实渠道、发送能力、Redis、Celery、RAG 或既有审核/DNC/Agent run 状态机改造。
- 每个 PR 先完成测试，等待 review 后才中文提交与推送；合并后同时删除本地和远端分支。

## X9 身份桥接契约

当前 X9 是服务端 Cookie Session，尚无可供 Agent 使用的 JWT 或服务间身份接口。本轮只建设 Agent 侧 Adapter、验证和测试替身；真实 X9 桥接须在 X9 项目中独立交付后再联调。

未来 X9 在自身服务内验证 Session 后，向 Agent 发出短期 HMAC-SHA256 签名身份断言：

- `X-X9-Identity`：Base64URL canonical JSON；
- `X-X9-Identity-Signature`：对原始 JSON 字节的 HMAC-SHA256 签名；
- `X-X9-Identity-Key-Id`：密钥轮换标识；
- claims：`issuer`、`audience=x9-replychat-agent`、`subject_id`、`display_name`、`issued_at`、`expires_at`、`request_id`；最长有效期 120 秒，允许 30 秒时钟偏差。

Adapter 仅使用 `.env` 或受管 Secrets 中的密钥。签名、issuer、audience 或时间无效返回 `401`；身份有效但 Agent 未预配置、成员停用或没有能力返回 `403`。外部 subject 以 `identity_source + external_subject` 唯一标识，邮箱和显示名绝不作为授权主键。

真实 X9 联调仍必须使用受信网络与 TLS/mTLS，且日志不得记录身份断言或签名。当前分支尚未实现 `request_id` 的一次性重放防护；它是未来 X9 网关或 Agent 侧持久化防重放设计的独立前置项，不能被本地 HMAC 契约替代。

## 权限模型

新增授权目录；历史数据迁移会将目录和领域表的 `department_code` 规范化为统一的受保护码：

- `auth_users`：外部身份到内部用户的稳定映射；
- `departments`：授权部门目录；
- `user_department_memberships`：一位用户在一个部门中的唯一角色和启用状态；
- `authorization_audit_events`：授权变更的追加式审计。

新外键全部显式使用 `RESTRICT`，成员关系只允许 `operator`、`reviewer`、`admin`。

| 角色 | 部门内能力 |
| --- | --- |
| `operator` | 审核数据读取、已批准草稿复制/下载审计、全局参考资料读取。 |
| `reviewer` | 继承 operator；审核决定、模型重试、DNC 确认/驳回、手动创建 run。 |
| `admin` | 继承 reviewer；达人与全局资料管理、模拟入站、模拟出站指令查看、授权目录管理。 |

跨部门列表只返回授权数据；跨部门单项资源返回 `404`；同部门但能力不足返回 `403`。产品和参考资料定义为全局配置，所有已认证成员可读，仅管理员可写。

## 六个顺序 PR

### PR1：授权数据与纯策略层（当前分支）

- 新增授权目录模型、Alembic revision、完整 downgrade 和显式首管理员 bootstrap CLI。
- 新增不依赖 FastAPI、X9 或 Worker 的 `Principal`、角色、能力和部门策略模块。
- CLI 需要 `--confirm`，幂等地创建或恢复首个管理员、部门和成员关系；只在发生变更时记录 bootstrap 审计。
- 测试 SQLite 实际迁移升级/降级、约束、删除限制、CLI 幂等性、角色矩阵和 PostgreSQL DDL 编译。

### PR2：身份 Adapter 与当前主体

- 实现 `IdentityAdapter`、HMAC X9 Adapter、`get_current_principal` 和能力依赖。
- 新增 `/api/followup-agent/auth/me`；只返回展示身份、部门角色和能力。
- 默认 fail-closed；仅 `test`/`demo` 使用服务端 Fake Adapter，生产拒绝 demo 模式。
- 回归有效、过期、篡改、错误 issuer/audience、未知用户和停用成员的 `401` / `403`。

### PR3：全部读接口与部门作用域

- 为现有业务 GET 接口统一接入 Principal；`/health` 保持公开。
- 队列、详情、回复、run、审核决定、导出记录和模拟指令均按授权部门下推 SQL。
- 保持审核队列总数加页面数据的固定两条 SELECT 契约。

### PR4：全部写接口与服务端审计主体

- 为现有 POST/PUT/PATCH 接口按角色能力和部门归属授权。
- 删除审核决定、DNC、重试和导出请求体的 `actor_id`，相应 schema 设 `extra="forbid"`；审计主体只从 Principal 派生。
- 维持 DNC 阻断、模型重试 `409`、审核不可重排和“导出不等于发送”。

### PR5：管理员授权管理与审计

- 仅 admin 可创建/停用 Agent 用户、部门和成员关系；通过停用撤权，不提供物理删除。
- 管理员只能管理自身授权部门；首次管理员仍只能由 bootstrap CLI 建立。
- 每次授权变更写入 `authorization_audit_events`，并测试撤销立即生效与审计删除限制。

### PR6：工作台、演示和文档交付

- 工作台调用 `/auth/me`，展示身份和部门，并按能力隐藏或禁用操作；后端继续二次校验。
- 移除硬编码 `demo_operator` 与前端请求体 `actor_id`；demo seed 创建虚构角色和部门成员。
- Docker 演示仅在本机 demo 模式启用 Fake Adapter；更新启动说明、交接记录、缺口复盘和 X9 联调说明。
- 运行 Python 全量测试、前端测试/构建、Docker PostgreSQL 迁移与不同角色演示。
- Compose 在未配置 X9 HMAC 密钥时传入有效空 JSON 对象；只有显式切换到 `x9_assertion` 时才要求受管密钥，避免本机 demo 因未使用的 X9 配置失败。

### P1：部门目录与业务归属边界修复（当前分支，待 review）

- 新增 Alembic revision：从所有含 `department_code` 的领域表回填规范化部门码；只创建启用目录项，不创建成员关系或授权审计。后续前向 revision 会规范化目录和全部历史业务行，确保严格 SQL 部门范围筛选与目录码一致；最新前向 revision 使用与 API 相同的边界空白字符集，并先检查目录码碰撞与入站幂等键碰撞。所有相关 revision 的 downgrade 均保留规范化后的目录/业务数据，避免破坏后续授权关系或重新引入越权。
- `POST /access/departments` 同时检查目录与所有既有业务部门码；已存在或已使用的码一律返回 `409`，不能借创建接口扩大读取范围。
- 并发创建相同的全新部门时，数据库唯一约束是最终裁决；后到请求会回滚失败事务并返回同一语义的 `409`，不留下部门、成员关系或授权审计残留。
- 创建达人、PUT/PATCH 迁移达人时，先校验目标 `creator:manage`，再校验目标目录存在且启用；未知、停用或未授权码均不得成为新的业务归属。
- 回归覆盖遗留业务码认领、全新部门创建、活跃目录、未知/停用目录、SQLite upgrade/downgrade 回填与规范化、含制表符/换行的授权后历史回复详情/队列可访问性、规范化前的入站幂等键碰撞拦截、隔离 PostgreSQL 空库升级与全部前后端测试。

## 验收与外部前置条件

- 每一阶段都必须验证未登录 `401`、未授权 `403`、跨部门 `404` 的对应边界，且前端不能替代后端授权。
- 真实 X9 联调的外部前置条件是：X9 侧部署 Session 验证与签名断言出口、双方配置受管密钥并限制受信网络；在此之前只能称为“Adapter 契约已验证”。
- 不论 X9 接入状态如何，Agent 都不发送邮件、不创建外发请求或任务，复制/下载始终仅是人工交接。
