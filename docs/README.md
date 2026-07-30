# 文档中心

本目录保存 X9 ReplyChat Agent 的长期开发资料。根目录的 `README.md` 仅保留仓库入口和快速启动说明；详细规则、实施状态和运行手册均以本目录为准。

## 阅读顺序

1. [最终需求规格](final-requirements.md)：产品边界、验收标准和生产目标，是后续每次新增、修改或删除的前置检查依据。
2. [实现缺口复盘](implementation-gap-review.md)：当前代码已覆盖的能力与未完成范围。
3. [项目交接记录](project-handoff.md)：当前代码基线、模块职责和下一步实施顺序。
4. [开发与运行指南](development-guide.md)：本地运行、测试、接口、Worker 和数据模型说明。
5. [PostgreSQL 部署说明](postgresql.md)：Docker Compose、本地环境变量、Alembic 迁移与隔离 PostgreSQL 核心测试。
6. [Operator Workbench 四阶段计划与进度](operator-workbench-four-pr-plan.md)：工作台的 PR 拆分、已合并范围、遗留缺口与交付边界。
7. [Operator Workbench 演示指南](operator-workbench-demo.md)：容器化启动、受控样例数据和人工审核演示路径。
8. [Operator Workbench 简历要点](operator-workbench-resume-highlights.md)：基于已实现能力的中文项目表述。
9. [RBAC Foundation 与 X9 身份适配计划](rbac-foundation-plan.md)：本地授权目录、X9 身份断言契约、部门隔离与交付边界。

## 当前模块进度

Operator Workbench 的四个阶段均已合并到 `main`：GitHub PR #4 交付读模型、审核闭环与人工交接，GitHub PR #5 交付受控 demo seed、Docker、API 静态托管和演示材料。RBAC Foundation 已随 GitHub PR #7 合并到 `main`；PostgreSQL 原子多 Worker 领取与 Worker 审计已随 GitHub PR #9 合并。当前测试基础保留 SQLite 快速回归，并用一次性随机数据库运行真实 PostgreSQL 核心套件；详细范围见 [PostgreSQL 部署说明](postgresql.md)。

## 文档治理

- 实施任何模块前，先核对 `final-requirements.md` 和 `implementation-gap-review.md`；若实现与规格冲突，应先更新并评审规格，再修改代码。
- `final-requirements.md` 是目标状态，`implementation-gap-review.md` 是事实状态；两者不一致时，不得把目标误写成已实现。
- `project-handoff.md` 记录可验证的当前基线，不记录密钥、真实联系人信息或可识别的生产数据。
- 外接渠道和企业身份提供方尚未选定。渠道选型完成前，任何具体认证、同步或发送能力都不能作为既定需求实施。
- 不得将 API Key、数据库密码、访问令牌或 `.env` 内容写入本文档或提交到 Git。
