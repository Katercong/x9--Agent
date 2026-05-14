# 本地 desktop app 切换到远端 X9 数据库 —— 迁移方案

**目标**：本地 `x9_creator_desktop_system` 项目继续作为开发平台与 UI，但所有数据读写改成走远端 `http://192.168.1.168:18765/api/v1/*`。本地 SQLite 不再是 source of truth。

**前提（已完成）**
- 远端已有 `tk_creators` 表，130 行已从本地全量同步过去（`x9_sync_creators.py`）
- 双向 API 读写已用 `x9_smoke_test.py` / `x9_key_permissions.py` / `x9_read_tk_creators.py` 验证
- API key `TwXKU_xzfLt-kNj5b8IzSPxYi27KrcOyd-9DNppYPco` 有效且权限完整
- JSON 列双向编解码自动生效（写时 list/dict 入库，读时自动 decode）

---

## 架构对比

**当前**
```
Browser/UI  →  FastAPI (127.0.0.1:8000)  →  SQLAlchemy  →  creators.sqlite (60+ 列)
                                          ↘  其他本地表
```

**目标**
```
Browser/UI  →  FastAPI (127.0.0.1:8000)  →  RemoteRepo  →  HTTP  →  X9 API (192.168.1.168:18765)
                                          ↘  SQLAlchemy  ↘  其他暂不迁移的本地表（tags/review/log）
```

UI 与 FastAPI 路由器接口完全保持，只是数据层换成 HTTP 客户端。

---

## 已知功能差距（远端 API 不支持的查询）

本地 `routers/creators.py` 用了一堆 SQLAlchemy 表达式，远端 `?col=val` + `?q=` 实现不了：

| 本地用的 | 处理方式 |
|---|---|
| `Creator.handle.ilike("%foo%")` | 客户端 fetch 后用 Python `in` 过滤 |
| `Creator.followers_count >= min` | 客户端 fetch 后过滤 |
| `Creator.recommendation_status.in_([...])` | 客户端 fetch 后过滤（或拆分多次 GET 拼接） |
| `or_(...)` / `and_(...)` 复合布尔 | 客户端拼装 |
| `func.coalesce(...)` `case when` | 客户端实现 |
| 多键排序 (4 个 desc 链) | 客户端 `sorted(..., key=...)` |
| JOIN `CreatorTag` | 远端没该表 → 阶段 3 处理 |

130 行规模下客户端处理无压力。**长到 5K+ 行**时再让张扩展 API（加 `?col__gte=` `?col__like=` `?col__in=`），这是阶段 5 的事。

---

## 阶段 1：读路径迁移（30 分钟，2 个文件）

### 新建
- `backend/services/remote_creators.py`
  - `class RemoteCreatorRepo` —— HTTP 客户端封装
  - 方法：
    - `list_all() -> list[dict]` 拉所有行（缓存 60 秒，避免每次请求都打远端）
    - `get_by_id(id: int) -> dict | None`
    - `get_by_handle(platform: str, handle: str) -> dict | None`
    - `bulk_upsert(rows: list[dict]) -> dict`
    - `patch(id: int, **fields) -> dict`
    - `delete(id: int) -> dict`
  - 统一错误处理 + 超时 + 重试（3 次指数退避）

### 改写
- `backend/routers/creators.py`
  - 把 `select(Creator).where(...)` 全部换成 `repo.list_all()` + Python filter/sort
  - 保留所有 query string 参数（前端不动）
  - 路径影响：
    - `GET /api/creators` 列表（最大改动）
    - `GET /api/creators/{id}`
    - `GET /api/creators/by-status`
    - `GET /api/creators/queues/{queue_code}`
    - `GET /api/creators/products/{product_type}`
    - `GET /api/creators/collabs/{collab_type}`
  - `func.coalesce(Creator.bio, "")` → Python `(row.get("bio") or "")`
  - `case when ...` 优先级 → 在 Python 里 `priority_rank = {"P1":1, "P2":2, ...}.get(row["outreach_priority"], 99)`

### 不动
- `routers/process.py`（review 流程，依赖 `ReviewTask` 本地表）
- `routers/extension.py`（依赖 `ExtensionSession` 本地表）
- `services/tag_engine.py` `services/recommendation_engine.py`（依赖本地附属表）

### 验收
- 启动本地 app，访问 `127.0.0.1:8000/ui/`
- 列表展示 130 行（远端的）
- 各种筛选（platform、has_email、score 区间、handle 模糊匹配）行为跟之前一致
- 排序（按 recommendation_score、followers_count）正确
- 翻页正确

### 回滚
- 重命名 `routers/creators.py` → `creators_remote.py`，把原版 `creators.py.bak` 改回来
- 单文件 git revert 即可

---

## 阶段 2：写路径迁移（20 分钟，1-2 个文件）

### 改写
- `backend/services/collector_service.py`
  - 浏览器插件 / scraper 现在调这里 `Creator(...)` + `db.add()` + `db.commit()`
  - 改成 `repo.bulk_upsert([row_dict])`
  - 保留函数签名，调用方零改动

- `backend/services/pipeline.py`（如果它也写 Creator）
  - 同上

### 不动
- 其他 service 的写入（tag/review/log 暂不迁移）

### 验收
- 浏览器插件抓一个新达人 → 远端立刻能 GET 到
- 本地 SQLite 的 `creators` 表**不再增长**
- 已存在的 130 行更新（如手动改 outreach_priority）→ 远端的 row 也更新

### 回滚
- 单文件 git revert

---

## 阶段 3：附属表处理（1 小时，多文件）

阶段 1+2 完成后会发现：tag、recommendation、review 流程读不到完整数据，因为：
- `creator_tags` / `tag_definitions` 在本地 SQLite，远端 `tk_creators` 没有 tag 关联
- `creator_recommendations` 同上
- `review_tasks` 同上

### 选项 A（推荐）：把附属表也搬到远端
- 用 `x9_sync_creators.py` 当模板，针对每张表写一个 sync 脚本
- 远端建 `tk_creator_tags` / `tk_tag_definitions` / `tk_creator_recommendations` / `tk_review_tasks`
- service 层全切到 RemoteRepo

### 选项 B：附属表保留本地
- tag/recommendation/review 流程继续读本地 SQLite
- `Creator.id`（远端的 INTEGER）需要跟本地 `CreatorTag.creator_id`（VARCHAR）对齐 —— 麻烦
- 不推荐，因为 ID 不同步问题大

走 A，干净。

### 验收
- tag_engine 能跑：给某个 creator 打 tag → 远端 `tk_creator_tags` 多一行
- recommendation_engine 能跑：批量评分 → 远端 `tk_creator_recommendations` 多 N 行
- review_tasks 能跑：标记 review_status → 远端对应行更新

---

## 阶段 4：清理（15 分钟）

- 移除 `database/connection.py` 里 `Creator` 表的 `init_db` 创建
- 删除 `models/creator.py` 或标记为 deprecated
- `requirements.txt` 里如果有不再需要的 SQLAlchemy 子包，trim 掉
- 更新 README 说明：本地 SQLite 现在只存 logs 和 extension session 这种瞬态状态

---

## 阶段 5（未来）：让远端 API 变得更强

向张提需求清单：
- `?col__gte=` `?col__lte=` 区间查询
- `?col__like=foo%` 模糊匹配
- `?col__in=a,b,c` IN 列表
- `?order_by=col1:desc,col2:desc` 多键排序
- `?join=creator_tags` 简单 JOIN（或者搞一个 `/api/v1/views/<name>` 提供预定义视图）
- WebSocket 通道，行变化时 push 给所有订阅者（实时同步）

这些做出来之后阶段 1 里的「客户端过滤」可以下沉回服务端，性能恢复 SQL 级。

---

## 风险与注意事项

1. **网络是依赖项**
   - 公司 WiFi 断了 / 张电脑关机 → 本地 app 完全不能用
   - 缓解：RemoteRepo 加一个 60 秒读缓存，临时断网时 UI 还能展示最近的快照
   - 写入侧不能缓存（要么成功要么失败，让用户知道）

2. **延迟变化**
   - 之前本地 SQLite 查询 < 1 ms
   - 现在远端 GET ~50-200 ms（LAN 内）
   - 加缓存后大部分 UI 操作仍秒级响应

3. **ID 体系切换**
   - 本地 `Creator.id` 是 VARCHAR(120)（业务自定义 id）
   - 远端 `tk_creators.id` 是 INTEGER（自动分配）
   - 跨表关联（CreatorTag.creator_id 等）必须基于 (platform, handle) 而非 id —— 阶段 3 实现时统一改

4. **并发写**
   - 多用户同时改同一行 → 远端 last-write-wins
   - 短期不是问题（单人小团队），如果将来变多人协作要加 etag/版本号

5. **API key 泄露**
   - `.env` 文件不要 commit 进 git
   - `.gitignore` 已有 `.env`，确认一下还在
   - key 一旦泄露在公开仓库，立刻让张吊销并换新

---

## 启动配置

阶段 1 落地之前，本地 `.env` 加这两行：

```
REMOTE_API_URL=http://192.168.1.168:18765
REMOTE_API_KEY=TwXKU_xzfLt-kNj5b8IzSPxYi27KrcOyd-9DNppYPco
REMOTE_TABLE=tk_creators
```

---

## 给张的需求单（阶段 5 用，提前给他打个招呼）

> 我们这边 desktop app 已经全切到远端了，目前用客户端过滤跑得动 130 行。如果未来涨到 5K+ 行，麻烦帮 X9 API 加几个查询能力：
>
> 1. `?col__gte=` `?col__lte=` 区间过滤
> 2. `?col__like=` 模糊匹配（`%foo%` 形式）
> 3. `?col__in=a,b,c` IN 列表
> 4. `?order_by=` 支持多键（`col1:desc,col2:desc`）
> 5. 一个简单的预定义 JOIN 机制（或者命名查询里支持 join，类似 `creators_with_tags` 这种）
>
> 不急，等 desktop app 稳定运行一段时间再做。优先级最高的是 1 和 4，因为现在 UI 翻页排序最常用。

---

## 我建议的下一步

立刻动手 = 阶段 1（30 分钟）。改 2 个文件：
- 新建 `backend/services/remote_creators.py`
- 重写 `backend/routers/creators.py`

完工后你自己访问 `127.0.0.1:8000/ui/` 验证一遍：列表是不是从远端来的、筛选排序还正常。OK 之后再开阶段 2。

要我开始阶段 1 吗？
