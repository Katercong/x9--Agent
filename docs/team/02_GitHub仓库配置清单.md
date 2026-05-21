# 02 — GitHub 仓库配置清单

> 操作人:Rocky(仓库 Owner)
> 预计完成时间:30-45 分钟
> 仓库:https://github.com/X9X9project/X9_AI_system

按顺序逐项执行,每项前面的方框打钩。

---

## A. 仓库基本设置

打开 `Settings` 标签(只有 Owner 看得到)。

### A1. General

- [ ] **Default branch** 设为 `main`
- [ ] **Features** 区:
  - ✅ Issues(开启)
  - ✅ Discussions(可选,适合长讨论)
  - ❌ Wiki(关掉,统一用 `docs/`)
  - ❌ Projects(可选,小团队 Issue + Label 就够)
- [ ] **Pull Requests** 区:
  - ✅ Allow **squash merging**(默认勾选,作为推荐合并方式)
  - ❌ 取消勾选 Allow merge commits
  - ✅ Allow rebase merging(备用)
  - ✅ Always suggest updating pull request branches
  - ✅ Automatically delete head branches(PR 合并后自动删分支)
- [ ] **Archives** 区:
  - ✅ Include Git LFS objects in archives(如果用 LFS)

### A2. Collaborators and teams

- [ ] 在 `Settings → Collaborators` 添加团队成员的 GitHub 账号
- [ ] 推荐用 **Teams** 而非个人邀请,创建一个 `x9-developers` team
  - 团队权限设为 **Write**(可以推 feature 分支、提 PR,但不能改 settings)
- [ ] 保留 1-2 个 **Admin**:Rocky + 一个备份(防止你账号出问题没人救场)
- [ ] **永远不要** 给非员工 Admin 权限

---

## B. 分支保护(最关键)

打开 `Settings → Branches → Branch protection rules → Add rule`。

### B1. 保护 `main` 分支

- [ ] **Branch name pattern**:`main`
- [ ] ✅ Require a pull request before merging
  - ✅ Require approvals — **1**(团队小可以 1,长大后可调到 2)
  - ✅ Dismiss stale pull request approvals when new commits are pushed
  - ✅ Require review from Code Owners(配合 `.github/CODEOWNERS`)
- [ ] ✅ Require status checks to pass before merging
  - ✅ Require branches to be up to date before merging
  - 状态检查项(等 CI 跑过一次后才会出现在选项里):
    - `ci / lint-python`
    - `ci / lint-node`
    - `ci / test-python`(有测试后启用)
- [ ] ✅ Require conversation resolution before merging(PR 评论必须解决才能合)
- [ ] ✅ Require signed commits(**可选**,提高门槛,如果团队还在适应 Git 可以先不开)
- [ ] ✅ Require linear history(配合 squash merge,保持 main 历史是直的)
- [ ] ✅ Do not allow bypassing the above settings(**重要**,Admin 也要走流程)
- [ ] ❌ Allow force pushes(关掉)
- [ ] ❌ Allow deletions(关掉)

### B2. (可选)保护 `release/*` 或长期 hotfix 分支

如果之后引入了发布分支(目前用不到),用类似规则保护 `release/*`。

---

## C. CODEOWNERS

`.github/CODEOWNERS` 决定 PR 自动指派给谁 review。模板已经准备好,直接复制并调整:

```powershell
mkdir .github -ErrorAction SilentlyContinue
copy docs\team\templates\.github\CODEOWNERS .github\CODEOWNERS
notepad .github\CODEOWNERS   # 把里面的 @your-github-username 改成实际人名
```

文件内容大概长这样(已写在模板里):

```
# 默认所有改动都需要 Rocky 看
*                           @rocky-github-username

# 后端 Python 服务
/core/                      @rocky-github-username @backend-lead
/desktop/backend/           @rocky-github-username @backend-lead

# 前端
/web/                       @frontend-lead
/web-user/                  @frontend-lead

# 抓取工具
/scrapers/                  @scraper-lead

# 基础设施 / 部署 / 数据库 —— 必须 Rocky 看
/infra/                     @rocky-github-username
/.github/                   @rocky-github-username
**/migration*.py            @rocky-github-username
**/schema*.sql              @rocky-github-username
.env.shared.example         @rocky-github-username
```

记得 commit:
```powershell
git add .github/CODEOWNERS
git commit -m "chore: add CODEOWNERS for PR auto-review"
git push
```

---

## D. PR 和 Issue 模板

模板已经在 `docs/team/templates/.github/` 下。直接复制到 `.github/`:

```powershell
copy docs\team\templates\.github\pull_request_template.md .github\
mkdir .github\ISSUE_TEMPLATE -ErrorAction SilentlyContinue
copy docs\team\templates\.github\ISSUE_TEMPLATE\*.md .github\ISSUE_TEMPLATE\
git add .github/
git commit -m "chore: add PR and issue templates"
git push
```

提 PR 时,GitHub 会自动填入模板。

---

## E. Secrets and Variables(给 CI 用)

打开 `Settings → Secrets and variables → Actions`。

### E1. Repository Secrets(加密,不可读)

按需添加(目前 CI 还没要用到这些,先列着):

| Secret 名 | 用途 |
|---|---|
| `PG_TEST_PASSWORD` | CI 测试数据库密码 |
| `GMAIL_TEST_CLIENT_SECRET` | (不推荐) — Gmail OAuth 不建议在 CI 里跑,改用 mock |
| `DEPLOY_SSH_KEY` | 未来自动部署时用 |
| `CODECOV_TOKEN` | (可选)代码覆盖率上报 |

**永远不要**在普通 Variables 里放敏感信息,Variables 是明文。

### E2. Variables(明文,可读)

| Variable 名 | 用途 |
|---|---|
| `PYTHON_VERSION` | `3.11.9` |
| `NODE_VERSION` | `20.18.0` |
| `POSTGRES_VERSION` | `16` |

CI workflow 里用 `${{ vars.PYTHON_VERSION }}` 引用,统一调版本时只改一处。

---

## F. Actions 配置

### F1. Actions 权限

`Settings → Actions → General`:

- [ ] **Actions permissions**:Allow `X9X9project` actions and reusable workflows
  - 或更宽松:Allow all actions and reusable workflows
- [ ] **Workflow permissions**:Read repository contents and packages permissions
  - ✅ Allow GitHub Actions to create and approve pull requests(**关掉**除非用 Dependabot 自动合并)

### F2. 启用第一个 workflow

CI 模板已经准备好,在 `docs/team/templates/.github/workflows/ci.yml`。复制过去:

```powershell
mkdir .github\workflows -ErrorAction SilentlyContinue
copy docs\team\templates\.github\workflows\ci.yml .github\workflows\
git add .github/workflows/ci.yml
git commit -m "ci: initial lint + test workflow"
git push
```

push 后立刻去 `Actions` 标签看是否跑起来了。第一次跑会需要修一些环境问题,正常的。详见 **04 — CI/CD 与部署流程** 文档。

---

## G. 安全设置(强烈推荐,大部分免费)

`Settings → Code security and analysis`:

- [ ] ✅ **Dependency graph**(开)
- [ ] ✅ **Dependabot alerts**(开 — 依赖出现 CVE 会发邮件)
- [ ] ✅ **Dependabot security updates**(开 — 自动开 PR 修)
- [ ] ✅ **Dependabot version updates**(可选,会有比较多 PR)
  - 如果开,在仓库根创建 `.github/dependabot.yml`(模板里已附)
- [ ] ✅ **Secret scanning**(开 — 自动扫描 commit 里的密钥)
- [ ] ✅ **Push protection**(开 — 阻止把密钥推上来)— **强烈推荐**
- [ ] ✅ **Code scanning**(开 CodeQL — Python/JS 自动安全分析)

Push Protection 这一项:开启后,如果有人尝试 push 一个含 Gmail client_secret 格式字符串的 commit,GitHub 会直接拒绝。这能预防本次发生的密钥泄漏事件。

---

## H. Webhooks / 集成(可选)

`Settings → Webhooks` 和 `Settings → Integrations`:

- [ ] Slack / 飞书 / 钉钉机器人(可选):PR 提交、合并、CI 失败通知到群
- [ ] Codecov(可选):跟踪测试覆盖率变化

具体集成方式按工具文档。

---

## I. 仓库标签(Labels)管理

打开 `Issues → Labels`,确保以下 label 存在(GitHub 默认有几个,需要补齐):

| 名字 | 颜色建议 | 含义 |
|---|---|---|
| `bug` | 🔴 红 | 已确认的 bug |
| `feature` | 🟢 绿 | 新功能 |
| `tech-debt` | ⚪ 灰 | 重构、优化 |
| `docs` | 🔵 蓝 | 文档 |
| `priority:high` | 🟠 橙 | 高优先级 |
| `priority:low` | ⚪ 浅灰 | 低优先级 |
| `blocked` | 🟡 黄 | 被阻塞 |
| `good-first-issue` | 💚 浅绿 | 适合新人 |
| `dependencies` | 🔵 浅蓝 | Dependabot 自动加 |
| `security` | 🔴 深红 | 安全问题 |

可以用 [GitHub Label Sync](https://github.com/jesusvasquez333/verify-pr-label-action) 等工具批量管理,但 10 个 label 手工建一次就好。

---

## J. 最后验收

做完上面所有,模拟一遍完整流程验收:

- [ ] 用另一个账号(或自己开个测试分支)尝试**直接推 main** → 应该被拒绝
- [ ] 提一个测试 PR,确认:
  - PR 模板自动出现
  - 自动指派 reviewer(根据 CODEOWNERS)
  - CI 自动跑起来(初期可能 fail,先看到它在跑就行)
  - 至少 1 approve 之前合并按钮是灰的
- [ ] 在测试 PR 里故意写一个假的 `client_secret=GOCSPX-FAKE` → Push Protection 应该拒绝

全部通过 → 配置完成,可以拉新人。

---

下一步:[`03_本地开发环境.md`](./03_本地开发环境.md)
