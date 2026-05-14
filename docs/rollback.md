# 回滚指南

如果本次合并(2026-05-11)出问题,按下面操作回退到合并前状态。

## 所有备份在哪

`F:\backup\` 下:

```
F:\backup\
├── x9db_pre_merge_20260511_1349.sql        ← PostgreSQL 完整 dump (6.2 MB)
├── Database_database.db_pre_merge_20260511_1349   ← F:\Database\database.db 副本 (2.4 MB)
├── database_pre_merge_20260511_1349/        ← F:\Database 完整目录快照 (149.8 MB, 3557 文件)
└── autoboker_pre_merge_20260511_1349/       ← F:\X9_AI_system\Auto boker grab 完整目录快照 (711.1 MB, 7755 文件)
```

这些备份覆盖:数据库 + 所有代码 + 所有配置 + .venv + 所有日志。

## 完整回滚(回到 5 月 11 日合并前)

### 1. 停服

```powershell
# 停 core
.\core\stop.bat  # 或杀掉 :18765 进程

# 停 desktop
Get-NetTCPConnection -State Listen -LocalPort 8000 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 2. 还原 PostgreSQL

```powershell
.\infra\scripts\db_restore.ps1 F:\backup\x9db_pre_merge_20260511_1349.sql
```

会先 DROP SCHEMA public CASCADE,然后导入。**会丢失合并以来 postgres 上的所有写入**(主要是扩展抓的新 creator 和 raw_observations)。

### 3. 还原文件系统

```powershell
# 在 F:\X9_AI_system\ 里把 core/ 和 desktop/ 等清掉
Remove-Item F:\X9_AI_system\core -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\desktop -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\scrapers -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\tools -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\infra -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\extension-archive -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\docs -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item F:\X9_AI_system\README.md, F:\X9_AI_system\.env.shared, F:\X9_AI_system\.gitignore, F:\X9_AI_system\start_all.ps1 -Force -ErrorAction SilentlyContinue

# 还原 F:\Database
robocopy F:\backup\database_pre_merge_20260511_1349 F:\Database /E /MT:8

# 还原 Auto boker grab
robocopy F:\backup\autoboker_pre_merge_20260511_1349 "F:\X9_AI_system\Auto boker grab" /E /MT:8
```

完成后目录结构回到 5 月 11 日早上的状态。

## 部分回滚

### 只回滚 creator 表合并(不动其他)

```sql
-- 连 postgres
docker exec -it x9-postgres psql -U x9 -d x9db

-- 删本次插入的 2 条纯 A 来源记录(没有匹配 B 的)
DELETE FROM creators WHERE legacy_int_id IS NOT NULL
  AND (platform, handle) NOT IN (
    SELECT platform, handle FROM creators_pre_merge_view  -- 需要预先备
  );

-- 把 130 条更新过的记录恢复成 NULL(其实只有 COALESCE 补 NULL 才会动,不是覆盖)
-- 安全做法:跑 db_restore.ps1 整库还原。
```

实际上,migrate_v16 用 `COALESCE`,**没有覆盖任何 B 已有的字段**,所以"回滚 creator 合并"主要是删 legacy_int_id 列和 16 个 A 独有列。但这些列只是新增,留着也不影响其他代码。

**推荐:**不要做部分回滚。要回就回完整。

### 只回滚目录搬迁

把 core/、desktop/、scrapers/ 等还原到原位置:

```powershell
robocopy F:\X9_AI_system\core F:\Database /E /MOVE /MT:8
robocopy F:\X9_AI_system\desktop "F:\X9_AI_system\Auto boker grab\x9_creator_desktop_system" /E /MOVE /MT:8
# 把 scrapers/ tools/ 等手动放回 Auto boker grab\
```

但这会留下 postgres 的 schema 变更(legacy_int_id 等新列),所以要么也回 postgres,要么留着新列。

## 检查回滚是否成功

```powershell
.\tools\x9_creator_db_check.py
```

如果按合并前还原,应该看到:
- creators total: 164(不是 166)
- creators with legacy_int_id: 0(不是 132)
- creator legacy total: 132(没变)

## 不可回滚的事

- 备份本身被删了
- `creator_legacy` 表如果后续被 DROP 了(本次没做)
- 跑过 db_restore.ps1 之后,在那之前的所有 postgres 写入(扩展抓的新数据等)
- 推送到 192.168.1.171 生产实例的任何东西(本次没做,但提示)

## 备份保留期

- `F:\backup\*_pre_merge_*` 保留 **90 天**(到 2026-08-09),之后可以手动清理
- 之后每次 `db_backup.ps1` 跑出来的 `x9db_*.sql` 自由保留(建议保留 30 天)
