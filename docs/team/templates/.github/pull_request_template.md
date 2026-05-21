<!--
PR 提交前请检查 `docs/team/01_团队协作规范.md` 第 3 节。
标题用 Conventional Commits 风格:
  feat: 添加按 GMV 排序
  fix: Gmail 外联在 + 号收件人下 OAuth 报错
  data: 去重 creators 表
  refactor: 抽出 LLM router
-->

## 改了什么

<!-- 一句话描述。-->


## 为什么改

<!-- 关联的 issue 或来源。如果有 issue,写 `Closes #123`。-->

Closes #


## 怎么验证

<!-- Reviewer 如何确认这个 PR 是对的?例如:
- 启动 core,访问 /api/v1/creators?sort=gmv_desc,确认返回按 GMV 倒序
- pytest tests/test_creators.py 全过
-->


## 自检清单

- [ ] 本地能跑通(`start_all.ps1` 或对应的开发命令)
- [ ] `ruff check .` 不报错(Python 改动)/ `npm run lint` 不报错(前端改动)
- [ ] commit message 符合规范(没有 WIP、asdf 之类)
- [ ] 没有把 `.env.shared` / 数据库 dump / 私人配置带进来
- [ ] 改 schema 的话:有迁移脚本,有 downgrade,Rocky 已 review
- [ ] 改对外 API 的话:更新了 `docs/api*` 文档


## 影响范围 / 需要通知谁

<!-- 这个 PR 合并后,谁需要知道?(后端联调的人、前端、运维…) -->
