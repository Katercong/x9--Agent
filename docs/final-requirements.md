# X9 ReplyChat Agent 最终需求规格（V1）

## 1. 文档定位

本文是项目的目标需求基线。每次新增、删除或修改功能前，开发者必须先检查变更是否符合本文；若不符合，应先获得需求调整结论并同步更新本文。

## 2. 产品目标与不可突破的边界

系统服务于内部 BD/运营团队，帮助处理达人回复：接收消息、规则分类、整理上下文、生成回复草稿和下一步建议，并保留完整审计记录。

- AI 只能分类、整理、生成草稿与建议；不得自动应用非终态的 `suggested_status`，不得创建发送请求、选择发件账号或调用外部渠道。
- 目标能力仅允许 Gmail 人工确认投递：reviewer/admin 先人工编辑并批准锁定草稿，再由同一人完成第二次明确“确认发送”，Delivery Worker 才可投递。不存在定时发送、批量群发、自动首封建联、AI 自动回复或无需第二次确认的外发。
- 禁止引入 Redis、Celery、pgvector 或 RAG；异步任务继续使用 PostgreSQL 数据库队列和 Worker。Gmail Delivery Worker 只能消费已由第二次人工确认创建的投递请求。
- 真实 API Key、数据库密码、Gmail OAuth client secret、Token 加密密钥、OAuth refresh token 和 X9 服务间密钥只能存在于受管 Secrets 或本机 `.env`，绝不能进入代码、文档、测试、日志或 Git。

## 3. 渠道与消息

目标外接渠道为企业 Google Workspace Gmail；本文件定义的是未来交付要求，当前仓库尚未实现 Gmail OAuth、X9 webhook 或真实投递。

- Gmail 采用矩阵就绪的多账号模式：每个账号通过 OAuth 授权，绑定一个 ReplyChat 用户和一个部门；首版仅账号所有者可选择该账号发送，禁止共享代发和管理员代发。
- 首版 OAuth 仅申请 `openid`、`email` 与 `https://www.googleapis.com/auth/gmail.send`；不读取邮箱、联系人、草稿或附件。授权账号必须属于配置的企业 Workspace 域名。
- 真实入站由 X9 在自身完成 Gmail 同步后，经 TLS/mTLS 与签名 webhook 推送；ReplyChat 不读取 X9 数据库、不接收或转发 X9 Cookie。入站事件必须包含稳定 `event_id`、时间戳、部门、X9 creator ID、X9 Gmail account ID/邮箱、Gmail thread ID、Gmail message ID、RFC `Message-ID`、`Reply-To`/`From`、主题、正文与发生时间。
- 适配器必须区分外部入站消息与仅供上下文使用的历史出站消息；只有已验签、未重放、已映射且方向为入站的消息可触发处理流程。真实消息使用 `channel + external_message_id` 作为稳定幂等键，并保存上游稳定的消息及会话/线程标识。
- X9 creator ID 与 Gmail account ID 必须预先映射到 ReplyChat 本地达人和授权账号；未知映射进入待处理审计，不调用 AI、不自动建档、不允许发送。
- 仅允许可靠线程回复：单收件人、纯文本正文，收件人从入站 `Reply-To` 或 `From` 派生并锁定，主题、Gmail `threadId`、`In-Reply-To` 和 `References` 锁定。缺少映射、线程或 RFC 引用时不得发送，不得降级为新邮件；首版不支持 CC、BCC、附件或批量发送。
- 每个 Gmail 账号默认每日最多 40 封人工确认投递。Gmail 明确失败后才可人工再次确认；网络超时或结果未知时必须人工核验，绝不自动重试。
- Gmail 明确发送成功后，ReplyChat 仅以签名、幂等的审计回写通知 X9 邮件历史、线程和消息 ID；回写失败可重试，但绝不重发 Gmail，也不得自动改变达人最终业务状态。

## 4. 业务流程与人工审核

```text
外部或模拟入站消息
-> 幂等入库
-> 规则分类
-> 上下文构建
-> queued Agent run
-> Worker 调用 LLM 或生成受限草稿
-> JSON/Pydantic 校验与运行留痕
-> 人工审核队列
-> reviewer/admin 编辑并批准锁定草稿
-> 同一 reviewer/admin 第二次明确确认发送
-> Gmail Delivery Worker 投递并记录审计
```

- 规则分类是权威输入。默认目标配置为 `reply_followup_v2` + `deepseek-ai/DeepSeek-V3.2`，并传递 `extra_body={"enable_thinking": false}`；V4 Flash 才使用 `reasoning_effort=high`。
- 普通回复、资料不足、模型失败、JSON 失败和校验失败均进入人工审核；AI 输出永不直接推进业务状态。
- 批准草稿不是发送。仅已批准的普通回复可进入第二次发送确认；DNC、明确拒绝、退信/无效邮箱、关闭项、无映射、无授权账号、超限或缺少可靠线程引用的项均不得出现发送能力。
- 创建投递请求时及 Delivery Worker 调用 Gmail 前必须分别检查 DNC。已确认 DNC 永久阻断，待确认 DNC 也必须阻断既有草稿与发送。
- 退信：忽略，不创建普通 Agent run 或跟进任务。
- 明确拒绝：创建终态审核，由审核人确认后才将达人设为 `dropped`。
- 明确退订：立即停止后续 AI/导出，创建待确认 DNC；审核人确认后成为永久 DNC。已确认 DNC 的后续消息可以留作审计，但不得产生业务跟进或可导出草稿。

## 5. 数据、权限与审计

- 保留达人、入站回复、产品、参考资料、Agent run、DNC、跟进待办、出站指令和沟通事件等领域数据。
- 所有审计关联外键使用 `RESTRICT`/`NO ACTION` 语义，禁止以 `ON DELETE CASCADE` 删除审计记录。
- `inbound_replies.external_message_id` 非空；`agent_followup_runs.creator_id` 与 `inbound_reply_id` 非空并受外键约束；同一回复在 `queued` 或 `running` 状态最多一条 run。
- 待建设 Gmail 授权账号、X9 creator/mailbox 映射、X9 webhook 收据、可靠线程引用、人工确认投递请求、不可变投递事件、按账号每日计数与 X9 发送审计回写；这些均不得复用或修改历史 migration。
- 权限模型至少包含运营、审核、管理员；用户只能访问获授权部门的数据。身份提供方尚未选定，但必须预留企业身份集成边界。
- 部门码必须使用 PostgreSQL 中可重现的 ASCII slug（小写字母、数字、`-`、`_`）；迁移发现历史非 ASCII 或非法部门码时必须失败，不得依赖数据库 Unicode 大小写规则继续运行。
- 消息正文、AI run 和普通审计默认保留 24 个月，可按部门配置；已确认 DNC 永久保留。

## 6. 生产架构与可靠性

- API、X9 Adapter、未来渠道同步 Worker、LLM Worker 与 Gmail Delivery Worker 应独立容器运行，数据库使用受管 PostgreSQL；默认 demo/test 环境不得启动真实 Gmail Delivery Worker。
- 所有 schema 变更必须由 Alembic 执行；生产应用启动不得自动建表或修改 schema。
- 已发布 migration 不得依赖可变的应用规则；涉及规范化或数据修复时，必须将规则冻结在版本化模块或 revision 内，保证新环境可重复执行同一施工记录。
- 多 Worker 领取任务必须采用事务级原子机制（PostgreSQL 使用 `FOR UPDATE SKIP LOCKED` 或等价机制）。
- 保留并扩展短事务领取、120 秒 lease、claim token 条件回写、过期租约回收和错误留痕；同步失败应可重试、回补、告警和观测。
- 凭据必须加密存储、来源于受管 Secrets；生产需具备备份恢复、监控、告警和最小权限访问。
- Gmail OAuth 使用 Web Authorization Code + PKCE 与不可预测 `state`；refresh token 必须带 key ID 加密保存，断开授权或失效后立即禁止投递。X9 webhook 与审计回写必须验签、限时、防重放并通过受信网络传输。

## 7. 验收标准

- 非终态业务推进均需人工确认。AI 永不自主外发；真实 Gmail 仅可由已批准草稿的同一 reviewer/admin 完成第二次确认后，由 Delivery Worker 自动投递。
- 所有真实消息幂等、外键、部分唯一索引与审计删除限制均在隔离 PostgreSQL 测试环境验证；后端运行时与自动化测试不支持其他数据库。
- V2 在既有评测集上维持 JSON/Pydantic 通过率以及分类、动作、状态路由 100%；模型异常全部进入人工审核。
- 多 Worker 不会重复领取任务；过期租约和旧 Worker 延迟回写不能破坏正确状态。
- 跨部门数据不可读写；运营不能确认 DNC/终态；管理员操作有完整审计。
- Gmail 投递必须验证账号所有权、部门范围、预映射达人/邮箱、锁定收件人和可靠线程引用；DNC 在确认与实际调用前均阻断。明确失败允许人工重试，未知结果不自动重试；成功投递和 X9 审计回写均具备幂等留痕且不自动推进达人状态。
- 在 20 个部门渠道连接、每日 1,000 条消息的目标负载下，同步、队列和审核查询可用且有可观测指标。
