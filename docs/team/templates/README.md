# 模板文件目录

这个目录下的文件都是**模板**,需要复制到仓库的正式位置才能生效。
按顺序操作:

## 1. 环境变量模板

```powershell
copy docs\team\templates\.env.shared.example .env.shared.example
git add .env.shared.example
git commit -m "docs: add env template for team onboarding"
```

## 2. GitHub 模板(PR / Issue / CODEOWNERS / Dependabot)

```powershell
# 创建 .github 目录结构
mkdir .github -ErrorAction SilentlyContinue
mkdir .github\ISSUE_TEMPLATE -ErrorAction SilentlyContinue
mkdir .github\workflows -ErrorAction SilentlyContinue

# 复制模板
copy docs\team\templates\.github\pull_request_template.md  .github\
copy docs\team\templates\.github\CODEOWNERS                .github\
copy docs\team\templates\.github\dependabot.yml            .github\
copy docs\team\templates\.github\ISSUE_TEMPLATE\*.md       .github\ISSUE_TEMPLATE\
copy docs\team\templates\.github\workflows\ci.yml          .github\workflows\

# 编辑 CODEOWNERS,把 @your-github-username 替换成真实人名
notepad .github\CODEOWNERS

# 提交
git add .github/
git commit -m "chore: add GitHub PR/Issue/CODEOWNERS/CI/Dependabot config"
git push
```

## 3. Dev 专用 docker-compose(只有维护者用)

```powershell
# 复制到 dev 克隆的 infra/docker/(不是生产克隆)
copy docs\team\templates\infra\docker-compose.dev.yml ^
     F:\X9_dev\X9_AI_system\infra\docker\docker-compose.dev.yml
```

## 4. CONTRIBUTING.md

```powershell
copy docs\team\templates\CONTRIBUTING.md CONTRIBUTING.md
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING entrypoint"
```

## 5. 提交

把以上所有 commit 推上去:

```powershell
git push origin main    # 如果你已经在 main 上配的话
# 或者通过 PR 的方式合并(更规范)
```

---

完成后,模板文件的实际位置:

```
.env.shared.example                          ← 仓库根
.github/
  ├── CODEOWNERS
  ├── dependabot.yml
  ├── pull_request_template.md
  ├── ISSUE_TEMPLATE/
  │   ├── bug.md
  │   └── feature.md
  └── workflows/
      └── ci.yml
CONTRIBUTING.md                              ← 仓库根
infra/docker/docker-compose.dev.yml          ← 仅 dev 克隆
```

`docs/team/templates/` 这个目录本身可以保留(留作历史),也可以删掉。
