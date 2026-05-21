# Contributing to X9_AI_system

欢迎为 X9 系统贡献代码 / 文档 / Issue。

## 在开始之前

请完整阅读这套团队协作文档:

1. [`docs/team/00_总览与紧急事项.md`](docs/team/00_总览与紧急事项.md)
2. [`docs/team/01_团队协作规范.md`](docs/team/01_团队协作规范.md) — **必读**
3. [`docs/team/02_GitHub仓库配置清单.md`](docs/team/02_GitHub仓库配置清单.md) — 仓库管理员看
4. [`docs/team/03_本地开发环境.md`](docs/team/03_本地开发环境.md) — 新人入职必看
5. [`docs/team/04_CI_CD与部署流程.md`](docs/team/04_CI_CD与部署流程.md)

## 简版规则

- 分支命名:`feat/<描述>` / `fix/<描述>` / `chore/<描述>` / `docs/<描述>` / `data/<描述>` / `refactor/<描述>`
- Commit message:`<类型>: <一句话>`(Conventional Commits 简化版)
- 不能直接推 `main`,所有改动必须走 PR + 1 人 review
- 不要把密钥、数据库、`.env` 提交进 git
- 数据库迁移必须 Rocky review

## 报告安全漏洞

不要开公开 issue。直接邮件 Rocky:lqtluoxi@gmail.com。

## 提问

- 写代码相关的疑问 → 团队 Slack/钉钉群
- 流程相关 → 先看 `docs/team/`,没找到答案再问
