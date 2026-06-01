"""
qzrc 公司线索回填脚本 —— 多批次低频模式（避开访问风控）

策略：
  外层 batches × 内层 batch_size
  每批开始前重新拉缺字段的目标（避免重复处理已回填/已跳过的）
  逐条打开详情页，单条之间随机 item-delay
  命中验证码 → 立即停止当前批次（不继续刷剩余条目）
  批次结束后随机 batch-delay；如果刚命中验证码，下一批等更久（×3）
  --stop-on-captcha：任一批命中验证码就终止整个 run

用法：
  python scraper/qzrc_backfill.py --dry-run
  python scraper/qzrc_backfill.py --batches 3 --batch-size 10
  python scraper/qzrc_backfill.py --batches 4 --batch-size 5 \\
        --item-delay-min 15 --item-delay-max 35 --batch-delay-min 480 --batch-delay-max 900 --stop-on-captcha
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from datetime import datetime
from pathlib import Path

import httpx

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERROR] 缺少 playwright，请执行: pip install playwright")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from qzrc_scraper import (
    ApiCapture, BASE_URL, USER_DATA_DIR,
    enrich_qzrc_company, rnd_delay, _company_detail_cache,
)

BACKEND_BASE = os.getenv("COMPANYLEADS_BACKEND_URL", "http://127.0.0.1:8000").strip().rstrip("/")


def api_headers() -> dict[str, str]:
    token = os.getenv("COMPANYLEADS_API_TOKEN", "").strip()
    return {"X-CompanyLeads-Token": token} if token else {}


async def fetch_targets(client: httpx.AsyncClient, limit: int) -> list[dict]:
    """从后端拉所有缺简介/地址的 qzrc 公司，最多 limit 条。"""
    out: list[dict] = []
    page = 1
    while True:
        r = await client.get(f"{BACKEND_BASE}/api/companies", params={
            "platform": "qzrc", "page": page, "page_size": 100, "include_excluded": "true",
        }, headers=api_headers())
        d = r.json()
        items = d.get("items") or []
        if not items:
            break
        for it in items:
            if not it.get("company_description") or not it.get("company_address"):
                out.append(it)
                if len(out) >= limit:
                    return out
        if page * 100 >= (d.get("total") or 0):
            break
        page += 1
    return out


async def push_back(client: httpx.AsyncClient, lead: dict, extras: dict, dry_run: bool) -> bool:
    """ingest API 写回；后端按 (platform, platform_company_id) 去重更新现有行。"""
    payload = {
        "platform": "qzrc",
        "platform_company_id": lead.get("platform_company_id") or None,
        "company_name": lead["company_name"],
        "industry": lead.get("industry"),
        "size_range": lead.get("size_range"),
        "city": lead.get("city"),
        "company_address": extras.get("company_address") or lead.get("company_address"),
        "company_description": extras.get("company_description") or lead.get("company_description"),
        "contact_name": extras.get("contact_name") or lead.get("contact_name"),
        "source_url": f"{BASE_URL}/company/show/{lead.get('platform_company_id')}"
                      if lead.get("platform_company_id") else lead.get("source_url"),
        "source_mode": lead.get("source_mode", "job_seeker"),
    }
    if dry_run:
        return bool(extras.get("company_description") or extras.get("company_address"))
    r = await client.post(f"{BACKEND_BASE}/api/companies/ingest", json=payload, headers=api_headers())
    return r.status_code == 200


async def run_one_batch(
    client: httpx.AsyncClient, page, capture: ApiCapture,
    batch_idx: int, total_batches: int, batch_size: int,
    item_delay_lo: float, item_delay_hi: float,
    dry_run: bool,
) -> dict:
    """跑单批：拉 batch_size 条目标 → 逐条 enrich → 命中验证码立即停批返回。"""
    stats = {"opened": 0, "got_desc": 0, "got_addr": 0, "pushed": 0, "failed": 0,
             "captcha": 0, "stopped_by_captcha": False}
    targets = await fetch_targets(client, batch_size)
    print(f"\n[BATCH {batch_idx}/{total_batches}] 拉到 {len(targets)} 条待回填")
    if not targets:
        return stats

    for i, lead in enumerate(targets, 1):
        entry = {
            "platform_company_id": lead.get("platform_company_id"),
            "source_url": f"{BASE_URL}/company/show/{lead.get('platform_company_id')}"
                          if lead.get("platform_company_id") else lead.get("source_url"),
            "company_name": lead["company_name"],
        }
        _company_detail_cache.pop(entry.get("platform_company_id") or entry.get("source_url"), None)
        await enrich_qzrc_company(page, entry, capture=capture)
        stats["opened"] += 1

        # 命中验证码 → 立即停批，不继续处理剩余条目
        if entry.get("_qzrc_captcha"):
            stats["captcha"] += 1
            stats["stopped_by_captcha"] = True
            print(f"  [{i}/{len(targets)}] {lead['company_name'][:30]} → ⚠ 验证码，立即停止本批")
            break

        got_desc = bool(entry.get("company_description"))
        got_addr = bool(entry.get("company_address"))
        if got_desc:
            stats["got_desc"] += 1
        if got_addr:
            stats["got_addr"] += 1
        marks = []
        if got_desc:
            marks.append("简介")
        if got_addr:
            marks.append("地址")
        print(f"  [{i}/{len(targets)}] {lead['company_name'][:30]} → {'+'.join(marks) or '(无新字段)'}")

        if marks:
            ok = await push_back(client, lead, {
                "company_description": entry.get("company_description"),
                "company_address": entry.get("company_address"),
                "contact_name": entry.get("contact_name"),
            }, dry_run=dry_run)
            if ok:
                stats["pushed"] += 1
            else:
                stats["failed"] += 1

        # 单条间隔
        if i < len(targets):
            delay = random.uniform(item_delay_lo, item_delay_hi)
            print(f"      ↳ 等 {delay:.1f}s 后下一条")
            await asyncio.sleep(delay)

    return stats


async def backfill(
    batches: int, batch_size: int, dry_run: bool,
    item_delay_lo: float, item_delay_hi: float,
    batch_delay_lo: float, batch_delay_hi: float,
    stop_on_captcha: bool, post_captcha_multiplier: float,
) -> None:
    started_at = datetime.now()
    print(f"[INFO] qzrc 回填启动 @ {started_at.strftime('%H:%M:%S')}")
    print(f"[CFG]  batches={batches} batch_size={batch_size}  "
          f"item={item_delay_lo:.0f}-{item_delay_hi:.0f}s  "
          f"batch_delay={batch_delay_lo:.0f}-{batch_delay_hi:.0f}s")
    print(f"[CFG]  验证码策略：{'命中即终止整批 run' if stop_on_captcha else f'命中停批 + 下批 ×{post_captcha_multiplier} 冷却'}")

    total = {"opened": 0, "got_desc": 0, "got_addr": 0, "pushed": 0, "failed": 0, "captcha": 0}

    async with httpx.AsyncClient(timeout=15) as client:
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                USER_DATA_DIR, headless=False, channel="chrome",
            )
            page = await ctx.new_page()
            capture = ApiCapture()
            handler = await capture.make_handler()
            await page.route("**/*", handler)

            for batch_idx in range(1, batches + 1):
                stats = await run_one_batch(
                    client, page, capture, batch_idx, batches, batch_size,
                    item_delay_lo, item_delay_hi, dry_run,
                )
                for k in total:
                    total[k] += stats.get(k, 0)

                # 本批结束 → 决定下一步
                if stats["stopped_by_captcha"]:
                    if stop_on_captcha:
                        print(f"\n[STOP] --stop-on-captcha：第 {batch_idx} 批命中验证码 → 终止整个 run")
                        break
                    if batch_idx < batches:
                        cool = random.uniform(batch_delay_lo, batch_delay_hi) * post_captcha_multiplier
                        cool_min = cool / 60
                        print(f"\n[COOLDOWN] 验证码后冷却 {cool:.0f}s (≈{cool_min:.1f} min)")
                        print(f"           期间请在打开的浏览器里手动滑过验证（cookie 通常 60min 有效）")
                        await asyncio.sleep(cool)
                elif batch_idx < batches:
                    rest = random.uniform(batch_delay_lo, batch_delay_hi)
                    print(f"\n[REST] 本批结束，下一批前等 {rest:.0f}s (≈{rest/60:.1f} min)")
                    await asyncio.sleep(rest)

            await ctx.close()

    elapsed = (datetime.now() - started_at).total_seconds()
    summary = "(dry-run)" if dry_run else f"推送成功 {total['pushed']} 失败 {total['failed']}"
    print(f"\n[DONE] 共 {total['opened']} 条访问 / 简介 {total['got_desc']} / 地址 {total['got_addr']} / "
          f"验证码 {total['captcha']} / {summary} / 耗时 {elapsed/60:.1f} min")


def main():
    parser = argparse.ArgumentParser(
        description="qzrc 公司简介/地址回填 —— 多批次低频模式",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # 批次结构
    parser.add_argument("--batches", type=int, default=3, help="批次数")
    parser.add_argument("--batch-size", type=int, default=10, help="每批多少条")
    # 节奏
    parser.add_argument("--item-delay-min", type=float, default=8.0, help="单条间隔下限秒")
    parser.add_argument("--item-delay-max", type=float, default=20.0, help="单条间隔上限秒")
    parser.add_argument("--batch-delay-min", type=float, default=180.0, help="批后冷却下限秒 (3min)")
    parser.add_argument("--batch-delay-max", type=float, default=480.0, help="批后冷却上限秒 (8min)")
    parser.add_argument("--post-captcha-multiplier", type=float, default=3.0,
                        help="刚命中验证码后，下一批冷却时间×此倍数")
    # 验证码策略
    parser.add_argument("--stop-on-captcha", action="store_true",
                        help="任一批命中验证码就终止整个 run (默认是继续，但冷却更久)")
    # 其它
    parser.add_argument("--dry-run", action="store_true", help="只访问详情页，不写回后端")

    # 兼容旧参数：保留 --limit 作为一个 batches × batch_size 的快捷设置
    parser.add_argument("--limit", type=int, default=None,
                        help="兼容旧脚本：传入则忽略 --batches/--batch-size，按 (batches=1, batch_size=limit) 跑")

    args = parser.parse_args()

    batches = args.batches
    batch_size = args.batch_size
    if args.limit is not None:
        batches = 1
        batch_size = args.limit
        print(f"[COMPAT] 检测到 --limit={args.limit}，按单批 batch_size={args.limit} 跑")

    asyncio.run(backfill(
        batches=batches,
        batch_size=batch_size,
        dry_run=args.dry_run,
        item_delay_lo=args.item_delay_min,
        item_delay_hi=args.item_delay_max,
        batch_delay_lo=args.batch_delay_min,
        batch_delay_hi=args.batch_delay_max,
        stop_on_captcha=args.stop_on_captcha,
        post_captcha_multiplier=args.post_captcha_multiplier,
    ))


if __name__ == "__main__":
    main()
