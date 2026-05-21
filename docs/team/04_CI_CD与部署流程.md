# 04 — CI/CD 与部署流程

> 关心自动化和部署的人读。
> 当前阶段:你的 Windows 机器既是开发又是生产。这份文档给出 3 个演进阶段的方案。

---

## 0. 什么是 CI/CD,先看图

```
开发者          GitHub                  Rocky 的服务器
                                                
push feat/xxx                              
─────────────►                              
                CI 跑(自动)              
                ├─ Lint                   
                ├─ 单元测试               
                └─ 构建                   
                ↓                          
                绿了才让合 PR              
                ↓                          
开 PR 合并到 main ──────► (人工 / 自动) ────► git pull + 重启
```

**CI**(Continuous Integration)= push 上去自动跑检查。
**CD**(Continuous Deployment / Delivery)= 合到 main 自动部署。

我们分三个阶段演进。

---

## 阶段 1(立即):GitHub Actions CI + 手动部署

### 1.1 CI workflow

完整 workflow 模板在 `docs/team/templates/.github/workflows/ci.yml`。这是它做的事:

```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  lint-python:    # Python ruff check + format check
  lint-node:      # web/web-user eslint
  test-python:    # pytest(目前可能没多少测试,先放着等以后加)
  build-frontend: # 确保 web/web-user 能 build 通过
```

把模板复制到 `.github/workflows/ci.yml`,push 之后每次提 PR 都会自动跑。

### 1.2 第一次跑可能失败 — 怎么修

- **Python lint 红**:
  ```powershell
  ruff check . --fix         # 自动修能修的
  ruff format .              # 自动格式化
  git add -A && git commit -m "chore: ruff autofix"
  ```
  反复跑直到本地 `ruff check .` 不报错。

- **Node lint 红**:
  ```powershell
  cd web && npm run lint -- --fix
  cd ..\web-user && npm run lint -- --fix
  ```

- **测试挂**:看具体输出。最常见是测试连数据库连不上 —— 在 CI 里得用 service container(模板里已经配了 postgres 16)。

- **找不到某个 env 变量**:CI 里没有你 `.env.shared`,要么在 `Settings → Secrets` 里加,要么改测试代码用 mock。

### 1.3 渐进添加更多检查

第一版 CI 只跑 lint 和 build,先让它绿。然后逐步加:

- 单元测试覆盖率(`pytest --cov`,目标 60% → 80%)
- `mypy` 类型检查(Python)
- `tsc --noEmit`(TypeScript 类型检查)
- 数据库迁移脚本干跑(`python migrate_xxx.py --dry-run`)
- 前端 build size 检查

每加一项都要先让全员跑通,不要一上来就上一堆,会被骂。

### 1.4 手动部署

阶段 1 部署还是手动,但用脚本统一:

`F:\X9_AI_system\infra\scripts\deploy.ps1`(03 文档第 6.6 节有完整版):

```powershell
# 简化版本
cd F:\X9_AI_system
git pull origin main

# 看一下本次拉下来有没有新的 migration
git diff HEAD@{1} HEAD --name-only | findstr "migrate_v"
# 如果有,人工跑它们

# 重启
.\stop_desktop.bat
.\start_all.ps1

# 看几个 health endpoint
curl http://localhost:18765/api/v1/health
curl http://localhost:8000/health
```

记一下每次部署的时间和 commit hash,放在 `infra/scripts/deploy_log.md` 里。出问题好回查。

---

## 阶段 2(团队稳定后):Self-hosted Runner 自动部署

阶段 1 跑顺之后,可以让 GitHub Actions 自动 ssh 上你的机器跑 deploy。但你这台是 Windows 本地机,不暴露公网,所以用 **GitHub 的 self-hosted runner**:在你机器上跑一个长连接到 GitHub 的进程,它会拉任务下来执行。

### 2.1 安装 self-hosted runner

打开 GitHub 仓库 → `Settings → Actions → Runners → New self-hosted runner`,选 Windows x64,GitHub 会给你一段命令(类似):

```powershell
# 在 F:\github-runner\ 下解压
mkdir F:\github-runner
cd F:\github-runner
# (从 GitHub 复制具体下载命令)
.\config.cmd --url https://github.com/X9X9project/X9_AI_system --token <一次性 token>
.\run.cmd
```

如果想作为服务常驻:
```powershell
.\svc.sh install
.\svc.sh start
```

### 2.2 部署 workflow

新建 `.github/workflows/deploy.yml`:

```yaml
name: deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: self-hosted    # 跑在你机器上
    steps:
      - name: Run deploy script
        shell: pwsh
        run: F:\X9_AI_system\infra\scripts\deploy.ps1
        # 注意这个 workflow 不 checkout 代码,deploy.ps1 自己处理 git pull
```

合并到 main 就自动部署。

### 2.3 保护措施

- 部署前**自动备份数据库**(deploy 脚本里已经有 pg_dump 那一步)
- 部署后**自动 smoke test**:
  ```powershell
  $resp = Invoke-WebRequest http://localhost:18765/api/v1/health -UseBasicParsing
  if ($resp.StatusCode -ne 200) { 
      Write-Host "Smoke test failed, rolling back"
      # git reset --hard HEAD~1 然后再 start_all
      exit 1 
  }
  ```
- **失败时通知**:workflow 加 Slack / 飞书 webhook,失败发消息到群

### 2.4 Self-hosted runner 的注意事项

- runner 进程必须长期在你电脑上跑,你睡觉的时候关机就部署不了。考虑把这台机器配置成"开发用关屏不关机"
- runner 拥有你机器上的所有权限,**不要让外部 contributor 触发它**(`Settings → Actions → General` 关闭 fork PR 跑 workflow)
- runner 跑出的日志(以及临时文件)留在你机器上,定期清理

---

## 阶段 3(将来):迁移到真正的服务器

阶段 2 跑顺了之后,把"生产"从你机器上挪走。**不一定急**,但有几个信号说明该挪了:

- 你需要出差/休假,但服务不能断
- 团队规模到 10+,你机器顶不住
- 出过一次"我重启电脑导致用户访问不了"
- 数据量大到本地磁盘吃紧

### 3.1 推荐路径

1. **租一台云服务器**(阿里云/AWS/腾讯云,2C4G 起步,Ubuntu 22.04)
2. **把整个项目容器化**:不只是 postgres,把 core / desktop / web / web-user 都做成 docker image
   - 这是阶段 3 的最大工作量,建议至少 2 周
3. **写一个 `docker-compose.prod.yml`** 在服务器上拉起所有服务
4. **GitHub Actions 改为推镜像到 registry** + ssh 服务器 pull + 重启
5. **加一个反代**(nginx / caddy)+ HTTPS(Let's Encrypt 自动)
6. **数据库迁移**:从本地 postgres 容器 dump → restore 到服务器容器

### 3.2 在那之前应该做的准备

阶段 1/2 期间就可以陆续做:

- [ ] 把所有"硬编码 F:\... 路径"改成相对路径或环境变量
- [ ] 把所有"硬编码 localhost"改成可配的 host
- [ ] 写 `Dockerfile` 给 core 和 desktop(可以参考 `infra/docker/`)
- [ ] 前端构建产物不要 commit 进 git(`web/dist/` 已经 ignore 了,但 `web/dist-deploy/` 看起来还在)
- [ ] 集中日志(目前散在各处的 `logs/` 目录),用 docker 的 stdout

做完这些,阶段 3 就只是"在另一台机器上跑同样的东西"。

---

## 1. 数据库迁移在 CI/CD 中的位置

迁移是最容易出事的环节,单独说一下。

### 推荐的迁移管理方式

目前你的迁移脚本散在 `core/scripts/migrate_v*.py`,需要人工记得跑哪个。**建议引入一个简单的版本表**:

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_by TEXT,
    notes TEXT
);
```

每个迁移脚本最后插入自己的 version:

```python
def upgrade():
    # ... ALTER TABLE ...
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_version (version, applied_by, notes) VALUES (%s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            ("v21_add_creator_tags", os.getenv("USER", "unknown"), "Add tags JSONB column")
        )
    conn.commit()
```

写一个 `infra/scripts/migrate_pending.py`,扫描 `**/migrate_v*.py`,对照 `schema_version` 表,只跑没跑过的。

部署脚本里调用它:

```powershell
python infra\scripts\migrate_pending.py
```

这样以后任何人都不会忘记跑哪个迁移、也不会重复跑。

### 复杂迁移的拆分原则

如果一次迁移会做这些事:
1. 加列(快)
2. 给老数据 backfill(慢,可能锁表)
3. 加约束(NOT NULL)

**拆成 3 个独立的迁移**,分 3 次部署:
- 部署 1:加列,默认 NULL,部署完代码先兼容 NULL
- 部署 2:跑 backfill(可以分批,半夜跑)
- 部署 3:加 NOT NULL 约束 + 删兼容代码

这样每一步都可以快速回退,生产更安全。

---

## 2. 回滚流程

部署出事了怎么办。

### 2.1 应用代码出事(没有 schema 变更)

```powershell
cd F:\X9_AI_system
git log --oneline -5             # 找出上一个好的 commit
git reset --hard <good-commit>
.\start_all.ps1
```

注意:`git reset --hard` 只对**生产克隆**做。开发克隆不要这么干。

### 2.2 数据库迁移出事

如果新迁移有 `downgrade()`:
```powershell
python core\scripts\migrate_v21_add_creator_tags.py --down
```

如果 downgrade 也搞坏了(罕见),从备份恢复:
```powershell
# 部署脚本里每次都 dump 一份到 F:\backup\
docker exec -i x9-postgres psql -U x9 -d x9db < F:\backup\pre_deploy_20260520_143012.sql
```

### 2.3 数据损坏(被错误业务逻辑改坏的数据)

这个最难,因为部分数据可能已经被用户使用了:
1. **立刻停服**,防止继续污染
2. 找到上次正确的 dump
3. 评估:从 dump 全量恢复 vs 写脚本针对性修复
4. 全量恢复会丢一段时间的真实业务数据 → 通常不可接受
5. 写脚本修复:对照 dump 找差异,有选择地回滚

经验:涉及数据的 PR review 要格外严格,见 01 文档。

---

## 3. 监控和告警(阶段 2 之后)

阶段 1 不强求,但阶段 2 之后建议加:

| 监控项 | 工具(本地阶段) | 工具(阶段 3 上线) |
|---|---|---|
| 服务存活 | 一个 PowerShell 定时任务 curl 各 endpoint | UptimeRobot 免费版 |
| 错误日志 | logs/ 目录人工看 | Sentry |
| 数据库大小 | 本地脚本 | Datadog / Prometheus |
| 关键业务指标(每日邮件量等) | core 里的 dashboard | 同上 |

最低限度脚本(放到 `infra/scripts/health_check.ps1`,定时任务每 5 分钟跑):

```powershell
$endpoints = @(
    @{name="core";    url="http://localhost:18765/api/v1/health"},
    @{name="desktop"; url="http://localhost:8000/health"}
)
foreach ($e in $endpoints) {
    try {
        $r = Invoke-WebRequest $e.url -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -ne 200) { throw "status=$($r.StatusCode)" }
    } catch {
        # 发飞书 webhook
        $body = @{ msg_type="text"; content=@{ text="[ALERT] $($e.name) 挂了: $_" } } | ConvertTo-Json
        Invoke-WebRequest -Uri "<飞书 webhook>" -Method POST -Body $body -ContentType "application/json"
    }
}
```

---

## 4. 备份策略

### 4.1 每天自动备份

`infra/scripts/db_backup.ps1` 已经存在,确认有 Windows Scheduled Task 在调用它。

推荐节奏:
- **每天 03:00 全量备份**,保留 14 天滚动
- **每次部署前**自动备份(部署脚本已经有了)
- **每月 1 号**手动把备份再传一份到云存储(阿里云 OSS / S3),保留 1 年

### 4.2 验证备份能用

至少**每季度**做一次"恢复演练":
1. 起一个测试 postgres 容器
2. 把最新备份 restore 进去
3. 起 core / desktop 指向这个测试 DB
4. 跑 smoke test,确认能用

没演练过的备份等于没备份。

---

## 5. 总结:你现在应该做什么

按"现在 → 1-2 周内 → 1-3 个月内"排序:

### 现在(本周)
- [ ] 把 `docs/team/templates/.github/workflows/ci.yml` 复制到 `.github/workflows/ci.yml`,push,跑通第一次 CI
- [ ] 在 `infra/scripts/` 下完善 `deploy.ps1`(自动 pg_dump 备份 + git pull + 重启 + smoke test)
- [ ] 引入 `schema_version` 表,写 `migrate_pending.py`

### 1-2 周内
- [ ] CI 加上单元测试,核心模块至少 30% 覆盖
- [ ] 完善 `health_check.ps1` 监控脚本,接飞书/钉钉告警
- [ ] 写每次部署后的"smoke test 清单"贴在 PR 模板里

### 1-3 个月内
- [ ] 装 self-hosted runner,实现 main → 自动部署
- [ ] 开始给 core / desktop 写 Dockerfile,为阶段 3 准备
- [ ] 评估是否租云服务器,做技术方案

---

📎 全套文档结束。回到 [`00_总览与紧急事项.md`](./00_总览与紧急事项.md)。
