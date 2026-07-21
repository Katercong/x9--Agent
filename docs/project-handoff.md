# 项目交接记录

> 最后更新：2026-07-21。目标规格见 [final-requirements.md](final-requirements.md)，当前实现范围见 [implementation-gap-review.md](implementation-gap-review.md)。本文只描述已验证的代码基线和接手顺序。

## 代码基线

- 远端主分支基线：`main` 的 `8951f15 docs: 归档并更新项目开发文档 (#1)`。
- 当前功能分支：`feat/human-review-workflow`，截至 `e3d84e9 feat: 增加草稿导出审计和终态待审保护`；该分支已推送但尚未合并。
- 最近全量验证：`python -m pytest -q`，结果为 `68 passed`；只有 FastAPI `on_event` 既有弃用警告。空本地 PostgreSQL 数据卷已重新迁移到 `9c7a4d1e2b3f (head)`，关键完整性约束已实际验证。
- 本地数据库：Docker Compose 管理 PostgreSQL，schema 由 Alembic 初始迁移创建；SQLite 仅保留用于自动化测试和可丢弃的本地 MVP 数据。

## 当前系统能力

```text
模拟入站回复
-> 确定性幂等入库
-> 关键词规则分类
-> 上下文构建
-> queued Agent run
-> 单 Worker 领取与 LLM JSON 输出
-> JSON/Pydantic 校验和运行留痕
-> need_ai_review
-> 人工审核队列
-> 普通回复：批准最终草稿或关闭不使用草稿
-> 已批准草稿：人工复制/导出并记录快照（系统不发送）
```

- 规则分类、DNC、退信、拒绝、资料不足和模型异常均有对应分流；拒绝和明确退订不再由系统直接完成终态业务决定，而是进入只读终态待审队列。
- 现有 Worker 使用短事务领取、120 秒租约、claim token 条件回写和过期回收，避免慢模型调用长期持有 SQLite 写锁。
- 当前只支持模拟消息；外接渠道和身份提供方均待选。没有自动发送、没有真实渠道接入、没有前端工作台。
- 人工审核后端已提供待审队列、普通回复决议、最终草稿和导出快照审计；`actor_id` 目前只用于留痕，不构成认证或授权。
- 系统不使用 Redis、Celery、pgvector 或 RAG。

## 代码定位

| 位置 | 职责 |
| --- | --- |
| `app/main.py` | FastAPI 应用与路由入口。 |
| `app/models.py` | SQLAlchemy 数据模型与约束。 |
| `app/schemas.py` | Pydantic 请求、响应和 LLM 输出结构。 |
| `app/services.py` | 业务流程、分类、上下文和持久化服务。 |
| `app/llm.py` | 硅基流动 OpenAI 兼容调用与提示词处理。 |
| `app/worker.py` | 数据库队列 Worker、租约和条件回写。 |
| `alembic/` | 数据库迁移脚本。 |
| `tests/` | API、Worker、约束和回归测试。 |

## 近期已完成的关键提交

- `29bd7c1 fix: 修复 PostgreSQL 初始迁移数据完整性约束`
- `64bc202 feat: 新增人工审核审计数据模型`
- `32a0fd3 feat: 新增普通回复人工审核接口`
- `e3d84e9 feat: 增加草稿导出审计和终态待审保护`
- `e8b83fc fix: 完善Worker异常留痕和跳过状态`
- `7d7df83 fix: 拆分LLM任务领取事务并增加租约回收`
- `c865bd0 test: 完善V3.2提示词评测与交接材料`
- `c3c07c5 test: 完善异步LLM流程评测和运行说明`
- `dec65c9 feat: 新增拒绝分流和模拟出站指令`

## 接手时的优先顺序

1. 将默认提示词和模型切换到已评测的 V2 + DeepSeek V3.2，并补齐回归评测。
2. 建设用户、部门成员关系与 RBAC，再让审核权限和终态确认写操作落到实际接口。
3. 建设前端人工审核工作台、终态确认/DNC 解除流程与站内通知，保持“系统不自动外发”的边界。
4. 完善 PostgreSQL 多 Worker 领取、容器化 API/Worker、监控、告警、备份与恢复。
5. 在渠道选型明确且补充详细规格后，再实现渠道适配、同步、待匹配队列和人工交接。

每一步开始前都应重新阅读最终需求和实现缺口；若范围变化，先更新文档并获得 review，再进入代码实现。
