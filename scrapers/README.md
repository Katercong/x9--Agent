# Scrapers — 抓取工具集

这里是 X9 系统的"手工"抓取工具。**它们目前是命令行运行,输出 CSV/JSON 文件**,不直接写数据库。

## 工具清单

### `youtube_email_grabber.py`

通过 yt-dlp 搜 YouTube 频道,从视频描述和频道 About 页提取邮箱。

```powershell
py -3.11 youtube_email_grabber.py --queries queries.txt --output output/youtube_emails.csv
```

输出:
- `output/youtube_emails.csv` — 14 列,每行一个找到的邮箱记录
- `output/youtube_emails_verification_queue.csv` — 需要人工审核的疑似邮箱

### `tiktok_profile_filter.py`

用 Playwright 浏览器自动化,搜 TikTok 关键词,筛选满足 follower/like 阈值的创作者。

```powershell
py -3.11 tiktok_profile_filter.py
```

输出:`tiktok_targets.json`(本地文件,append-only)。

### `webui.py`

YouTube 抓取器的 Flask Web UI,运行在 `:8765`。把命令行运行包装成网页操作 + 实时日志。

```powershell
py -3.11 webui.py
```

浏览器打开 `http://localhost:8765`。

## 为什么不直接入库

历史原因。Chrome 扩展走的是 `POST :8000/api/local/extension/x9-compat/ingest-creators`,而这两个 CLI 抓取器是单机离线运行,输出文件供人工或后续工具消费。

## 如何把 CSV/JSON 喂回数据库(未来)

两条路:

### 路径 A:扩展统一(推荐)
让 YouTube 抓取器也调 `/api/local/extension/x9-compat/ingest-creators`。需要把它的 CSV 行转成扩展 v1.0.19 格式的 JSON payload。这是新代码,本期没做。

### 路径 B:批量导入(快速)
写一个 `core/scripts/import_youtube_csv.py`,从 `output/youtube_emails.csv` 读,批量 `INSERT INTO creators` 走 postgres。模板可以参考 `core/scripts/import_creators.py`。

把 TikTok JSON 同理处理。

## 历史接入

`tools/x9_sync_creators.py` 曾经把 desktop SQLite 同步到远程 X9 API。**现在 postgres 是单一数据源,这个工具基本作废**。保留作为参考。
