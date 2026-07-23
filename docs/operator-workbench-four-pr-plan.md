# Operator Workbench 四阶段实施计划

> 状态：已评审的实施计划；事实完成状态仍以 `project-handoff.md` 与每个 PR 的测试结果为准。

## 共同边界

- 工作台只覆盖 Agent 人工审核闭环；不得接入 X9、Gmail、IMAP 或任何真实外部渠道，也不得自动发送消息。
- 页面可参考通用的左队列、中详情、右操作栏工作节奏，但不得复制 X9 源码、品牌样式、组件、真实数据或业务文案。
- AI 只提供分类、上下文、草稿与建议；任何最终决定、复制或导出都由人工显式触发。
- 无登录模式下审核审计身份固定为 `demo_operator`。它仅是演示审计字段，不是认证或 RBAC 实现。
- 每个 PR 完成后运行对应测试并等待 review；未经确认不提交或推送。

## PR 1：`feat/review-read-model-api`

- 在 `review-queue` 中新增 `model_failure` 分类。
- 新增 `GET /review-items/{reply_id}` 聚合详情接口。
- 补齐四类队列、详情聚合与终态只读的后端测试。
- 不新增前端、Docker、演示种子或数据库 schema 变更。

## PR 2：`feat/operator-workbench-core`

- 建立 React + Vite + TypeScript + Ant Design + TanStack Query。
- 开发态由 Vite 代理 `/api`。
- 实现三栏：队列、上下文详情、审核操作；直接调用 PR 1 的真实 API。
- 普通项可编辑并批准或关闭；拒绝只读；待确认 DNC 可由人工确认并转为永久 DNC，或驳回并重新进入普通 Agent 审核；模型失败可由人工明确重试。上述操作均不提供发送或导出。
- 模型失败项明确显示“模型未生成可用建议”，允许人工从空白草稿起草后批准。
- 不实现复制、下载、Docker 或生产静态托管。

## PR 3：`feat/operator-workbench-export`

- 审核批准后提供复制与 `.txt` 下载。
- 每次人工交接动作调用既有导出审计接口。
- 工作台新增“草稿生成中”和“已批准草稿”分类：前者仅展示运行状态，后者仅提供人工交接。
- 补“导出不等于发送”与“DNC 无导出入口”的测试。
- 为未来渠道集成保留禁用的“发送（暂未接入）”按钮，以及只读 `delivery-capability` 能力接口；二者都不得创建外发任务、写入发送记录或调用外部渠道。

## PR 4：`feat/demo-delivery`

- 提供受控 demo seed 脚本。
- 新增 Dockerfile、Compose `migrate` 服务、API 静态托管与可选 Worker profile。
- 在 `docs/` 编写演示文档、启动说明与简历项目要点。
- 验证镜像构建和健康检查。
