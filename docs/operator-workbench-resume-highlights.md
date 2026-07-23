# Operator Workbench 项目简历要点

以下内容基于当前已实现能力，可按岗位要求选择使用。

- 设计并实现面向 BD/运营的三栏人工审核工作台，整合 PostgreSQL 审核队列、达人与产品上下文、Agent 运行留痕、草稿编辑和人工交接审计。
- 将 LLM 输出约束为 JSON 与 Pydantic 契约，覆盖模型失败、JSON/校验失败、人工重试及完整 run 留痕，确保 AI 只提供建议、不自动推进业务状态。
- 实现 DNC 优先级与终态安全边界：待确认/已确认 DNC 阻断草稿、导出和后续 AI 处理；历史会话不会重复展示为可操作 DNC 项。
- 使用 React、TypeScript、Ant Design 与 TanStack Query 构建会话式工作台，支持人工编辑、批准锁定、复制和 `.txt` 下载，并记录导出快照而非自动发送。
- 采用 Docker Compose 编排 PostgreSQL、Alembic migrate、FastAPI 静态托管与可选 Worker profile；提供幂等、无真实数据且不调用模型的 demo seed，支持一键复现审核演示。
