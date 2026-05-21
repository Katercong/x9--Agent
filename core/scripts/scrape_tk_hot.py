"""TK 热搜抓取调度器（模板）

廖：复制这个文件改名 scrape_tk_hot_real.py，把 fetch_keywords() 里的 demo
逻辑替换成你真实的爬虫（TikTok Creator Center / 浏览器自动化 / 第三方 API
如 Pentos/TikBuddy 等任选）。

工作流：
1. 创建 scrape_run 记录（status='running'）
2. 调用 fetch_keywords() 抓数据
3. 调 API /api/v1/data/tk_hot_keywords/bulk 批量 upsert
4. 关闭 scrape_run（status='done' 或 'failed' + 统计）

定时调度建议：
- Linux/Mac: crontab `*/30 * * * * cd /path && python scripts/scrape_tk_hot.py >> log 2>&1`
- Windows: 任务计划程序，触发器"每 30 分钟"，操作=python.exe + 此脚本绝对路径
- 或者：用现成的 schedule / APScheduler 库写一个常驻进程

使用方式：
    python scripts/scrape_tk_hot.py                       # 默认: 30 个关键词，演示数据
    python scripts/scrape_tk_hot.py --source demo --n 50  # 显式参数
    python scripts/scrape_tk_hot.py --source real         # 调你的真实抓取
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "database.db"
API_KEY_FILE = ROOT / ".api_key"

# 服务器端口（与 run.bat 的 PORT 保持一致）
API_BASE = os.environ.get("X9_API_BASE", "https://usx9.us")


def get_api_key() -> str:
    """读取一个有效的 admin API key。优先从环境变量，其次从 .api_key 文件。"""
    k = os.environ.get("X9_API_KEY")
    if k:
        return k.strip()
    if API_KEY_FILE.exists():
        return API_KEY_FILE.read_text(encoding="ascii").strip()
    raise RuntimeError("找不到 API key — 请把 admin token 放进环境变量 X9_API_KEY 或文件 .api_key")


# ============================================================
# 演示数据生成器（廖：替换为真实抓取）
# ============================================================
DEMO_BASE_KEYWORDS = [
    # 模拟从 TT 热搜抓的常见词，每次跑会随机加噪声模拟数据变化
    ("period underwear", "female_care", 220000, 0.18),
    ("organic cotton pads", "female_care", 95000, 0.34),
    ("dog diapers male", "pet", 88000, 0.42),
    ("leak proof dog pad", "pet", 41000, 0.28),
    ("postpartum recovery pads", "adult_care", 35000, 0.36),
    ("ultra thin baby diapers", "baby", 47000, 0.16),
    ("bed pads incontinence", "home_care", 39000, 0.22),
    ("activated charcoal pads", "home_care", 19000, 0.41),
    # 模拟"突然冒出来"的新关键词（每次跑随机出现）
    ("biodegradable period pads", None, None, None),
    ("sensitive skin overnight", None, None, None),
    ("training pads scented", None, None, None),
    ("dog pee pad odor", None, None, None),
]


def fetch_keywords_demo(n: int) -> list[dict]:
    """模拟抓取：在基础词上加随机扰动，模拟真实抓取的数据变化。

    廖把这个函数替换成真实抓取逻辑：
        from playwright.sync_api import sync_playwright   # 浏览器自动化
        # 或
        import requests; r = requests.get('https://api.pentos.co/...')  # 第三方 API
        # 或
        # 解析 TT Creator Center 公开页面
    """
    out = []
    base = random.sample(DEMO_BASE_KEYWORDS, min(n, len(DEMO_BASE_KEYWORDS)))
    for i, (kw, cat, vol, growth) in enumerate(base):
        # 实际抓取数据时通常带噪声
        if vol is not None:
            vol = int(vol * random.uniform(0.85, 1.20))
        if growth is not None:
            growth = round(growth + random.uniform(-0.08, 0.12), 3)
        out.append({
            "keyword": kw,
            "source_platform": "tiktok",
            "region": "US",
            "category_hint": cat,                 # NULL 时由 trigger 启发式补
            "search_volume": vol,
            "growth_rate": growth,
            "rank_position": i + 1,
            "last_seen_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return out


# ============================================================
# 真实抓取（廖：在这里写你的代码）
# ============================================================
def fetch_keywords_real(region: str = "US") -> list[dict]:
    """⚠ 占位 — 廖在这里实现真实的 TT 热搜抓取。

    参考思路：
    1. Playwright 模拟登录 TT Creator Center → 解析 trends 页面
    2. 调 Pentos / TikBuddy / TokBoard 等第三方 API（要 key）
    3. 抓 TT 公开 hashtag 页面（脆弱、易反爬）
    4. 用 RapidAPI 上的 TT trending 端点（要付费 key）

    返回格式跟 fetch_keywords_demo 一致（list of dict）。
    """
    raise NotImplementedError(
        "⚠ 真实抓取未实现 — 廖请在 scripts/scrape_tk_hot.py 的 fetch_keywords_real() 里写"
    )


# ============================================================
# Run management
# ============================================================
def start_run(*, source: str, region: str, triggered_by: str) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(
        "INSERT INTO scrape_run(source, region, triggered_by, status) VALUES(?,?,?, 'running')",
        (source, region, triggered_by)
    )
    rid = cur.lastrowid
    con.commit()
    con.close()
    return rid


def finish_run(*, run_id: int, n_added: int, n_updated: int, n_errors: int,
               status: str, error_message: str | None = None, notes: str | None = None) -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "UPDATE scrape_run SET finished_at=datetime('now'), status=?, "
        "n_added=?, n_updated=?, n_errors=?, error_message=?, notes=? WHERE id=?",
        (status, n_added, n_updated, n_errors, error_message, notes, run_id)
    )
    con.commit()
    con.close()


def push_to_api(items: list[dict], api_key: str) -> dict:
    """通过 X9 API 批量 upsert，自动触发 snapshot 写入。"""
    r = requests.post(
        f"{API_BASE}/api/v1/data/tk_hot_keywords/bulk",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json={"items": items},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ============================================================
# Main
# ============================================================
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="demo", choices=["demo", "real"],
                   help="抓取来源 (demo = 演示数据 / real = 廖的真实代码)")
    p.add_argument("--region", default="US")
    p.add_argument("--n", type=int, default=12, help="演示模式抓多少条")
    p.add_argument("--triggered-by", default="cron",
                   choices=["cron", "manual", "webhook"])
    args = p.parse_args()

    api_key = get_api_key()
    run_id = start_run(source=args.source, region=args.region, triggered_by=args.triggered_by)
    print(f"[scrape] run_id={run_id} source={args.source} region={args.region}")

    try:
        if args.source == "demo":
            items = fetch_keywords_demo(args.n)
        else:
            items = fetch_keywords_real(args.region)

        print(f"[scrape] fetched {len(items)} keywords")
        if not items:
            finish_run(run_id=run_id, n_added=0, n_updated=0, n_errors=0,
                       status="done", notes="no items returned")
            return

        result = push_to_api(items, api_key)
        n_added = result.get("inserted", 0)
        n_updated = result.get("updated", 0)
        n_errors = len(result.get("errors", []))

        finish_run(run_id=run_id, n_added=n_added, n_updated=n_updated,
                   n_errors=n_errors, status="done")
        print(f"[scrape] OK — added={n_added} updated={n_updated} errors={n_errors}")
    except Exception as e:
        finish_run(run_id=run_id, n_added=0, n_updated=0, n_errors=1,
                   status="failed", error_message=str(e)[:300])
        print(f"[scrape] FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
