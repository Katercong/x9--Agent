# 本地部署手册

## 先决条件

- Windows 10/11
- Python 3.11(`py -3.11` 可执行)
- Docker Desktop 跑得起来
- Node.js LTS(只有要跑 Electron 才需要)

## 第一次设置

### 1. 启动 PostgreSQL 容器

```powershell
.\infra\scripts\db_init.ps1
```

第一次跑会:
- 创建 docker 卷 `x9_pgdata`
- 启动 `x9-postgres` 容器(postgres:16)
- 端口 `15432` 映射到容器的 `5432`

容器健康后会输出 `postgres is healthy (port 15432)`。

### 2. Python 环境

Core 和 Desktop 都用 `py -3.11`。需要的包:

```powershell
# Core
cd core
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Desktop
cd ..\desktop
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> 注:本次合并后,`core/.venv` 是 F:\Database 搬过来的旧虚拟环境,路径已失效。需要重建。

### 3. 验证数据库

```powershell
py -3.11 .\tools\x9_creator_db_check.py
```

应看到:
- creators total: 166
- creators with legacy_int_id: 132
- creator (legacy) total: 132
- product total: 44
- outreach total: 101
- 5 个关键索引存在

## 日常启动

```powershell
.\start_all.ps1
```

完成后:
- Desktop:`http://localhost:8000`
- 管理后台:`http://localhost:8000/`、`/a/*`、`/c/*`、`/d/*`
- 员工门户:`http://localhost:8000/portal/`

默认只启动 PostgreSQL + Desktop。需要 Core `/api/v1` 或 Core 产品库页面时:

```powershell
.\start_all.ps1 -StartCore
```

常用参数:

- `-NoBrowser`: 只启动服务,不自动打开浏览器。
- `-StartCore`: 同时启动 Core `:18765`。
- `-RequireCore`: Core 未健康时让脚本失败退出。
- `-OpenLocal`: 打开 `http://localhost:8000/portal/`,而不是线上域名。
- 日志目录:`F:\X9_AI_system\logs\`。

## 代码变更后的构建/部署

只修改 Markdown 文档时不需要重启后端,也不需要重新构建前端。

如果修改 `web/` 管理后台源码:

```powershell
cd F:\X9_AI_system\web
npm run build:root
npm run deploy:root
```

如果修改 `web-user/` 员工门户源码:

```powershell
cd F:\X9_AI_system\web-user
npm run build:deploy
npm run deploy
```

如果修改 `desktop/backend/` 或 `core/app/` 后端源码,部署后必须重启对应后端进程。否则线上进程可能仍使用旧代码。

## 变更后验收

整理性修复或部署后,至少执行:

```powershell
cd F:\X9_AI_system
py -3.11 -m pytest desktop\backend\tests -q

cd F:\X9_AI_system\web
npm run build

cd F:\X9_AI_system\web-user
npm run build
```

服务启动后检查:

- `http://localhost:18765`
- `http://localhost:8000/health`
- `http://localhost:8000/login`
- `http://localhost:8000/`
- `http://localhost:8000/portal/`
- `http://localhost:8000/api/local/auth/me`
- `http://localhost:8000/api/local/dashboard/unified`

完整清单见 `docs/system_boundary_and_acceptance.md`。

## 日常停服

Core 有自己的 stop:
```powershell
.\core\stop.bat
```

Desktop 直接 Ctrl-C 它的 uvicorn 窗口,或:
```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 | Stop-Process -Id { $_.OwningProcess } -Force
```

## 备份

```powershell
.\infra\scripts\db_backup.ps1
```

输出到 `F:\backup\x9db_YYYYMMDD_HHMM.sql`。

## 还原(谨慎)

```powershell
.\infra\scripts\db_restore.ps1 F:\backup\x9db_20260511_1349.sql
```

会先 `DROP SCHEMA public CASCADE` 再导入。脚本有二次确认。

## Chrome 扩展安装

桌面后端启动后:

```powershell
cd desktop
.\scripts\install_extension_strict.ps1
```

这会把 `archive/extensions/tiktok-creator-lead-browser-extension-1.0.19/` 加上 `chrome-extension-relay/` 的 x9_relay.js / x9_sw.js 注入到 Chrome 的扩展目录。

然后用扩展抓 1 个 TikTok 创作者,跑:
```powershell
py -3.11 .\tools\x9_creator_db_check.py
```
应该看到 `creators total` +1。

## 故障排查

### postgres 没启动 / port 15432 被占
```powershell
docker ps -a --filter "name=x9-postgres"   # 看状态
docker logs x9-postgres --tail 50          # 看错误
docker compose -f infra\docker\docker-compose.yml restart
```

### Core 启动报 sqlite3 错误
现在 main.py / pg_dashboard.py 都用 postgres。`v1.py` 仍读 SQLite(`core/database.db`),如果该文件丢失:
```powershell
# 用备份恢复
Copy-Item F:\backup\Database_database.db_pre_merge_20260511_1349 F:\X9_AI_system\core\database.db
```

### Desktop 启动报 ModuleNotFoundError: x9_creator_desktop_system
说明环境里残留了旧的 Python 缓存。清理:
```powershell
Get-ChildItem -Path F:\X9_AI_system -Recurse -Force -Directory | Where-Object { $_.Name -in @("__pycache__", ".pytest_cache") } | Remove-Item -Recurse -Force
```

### Desktop 报 401 但前端转圈
登录:`POST /api/local/auth/login` 用部门账号。第一次需要管理员审批。
