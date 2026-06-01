"""
大泉州人才网登录助手 — 仅用于保存登录状态

运行后会打开真实 Chrome 浏览器，手动完成登录，
登录成功后脚本自动检测并保存 session，之后 qzrc_scraper.py 直接复用。

用法:
  & "python" scraper/qzrc_login.py
  & "python" scraper/qzrc_login.py --mode job
"""

import argparse
import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERROR] 请执行: pip install playwright && playwright install chromium")
    sys.exit(1)

USER_DATA_DIR = str(Path(__file__).parent.parent / "data" / "browser-profile")
LOGIN_URL = "https://www.qzrc.com"  # 登录入口在主页弹窗，无独立登录页
JOB_LIST_URL = "https://www.qzrc.com/home/joblist"
RESUME_LIST_URL = "https://www.qzrc.com/home/resumelist?adv=true"


async def do_login(target_after_login: str) -> None:
    print("[INFO] 打开浏览器，请手动完成登录…")
    print(f"[INFO] 登录后将跳转到: {target_after_login}")

    async with async_playwright() as p:
        # 不加任何 route 拦截，保证页面完全正常加载
        ctx = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            channel="chrome",
        )
        page = await ctx.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("\n[等待] 请在浏览器窗口中完成登录，登录成功后脚本会自动检测并退出。")
        print("       如果一直未检测到，也可以直接按 Ctrl+C 退出（session 已保存）。\n")

        # 自动检测登录成功：等待 URL 不再含 "login"，或出现用户信息元素
        try:
            await page.wait_for_function(
                """() => {
                    const url = location.href;
                    if (!url.includes('login')) return true;
                    // 检测常见的登录成功标志
                    const selectors = [
                        '.user-name', '.username', '.avatar',
                        '.user-info', '#userinfo', '.logout',
                        'a[href*="logout"]', 'a[href*="signout"]'
                    ];
                    return selectors.some(s => document.querySelector(s));
                }""",
                timeout=300_000,  # 最多等 5 分钟
            )
            print("[SUCCESS] 检测到登录成功！")
        except Exception:
            print("[INFO] 未自动检测到登录成功，但 session 已保存到 browser-profile。")

        # 跳到目标页确认一次
        await page.goto(target_after_login, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print(f"\n[INFO] Session 已保存至: {USER_DATA_DIR}")
        print("[INFO] 现在可以关闭浏览器，然后运行爬虫：")
        print('       python scraper/qzrc_scraper.py --mode resume --inspect --max-pages 1 --keywords "跨境销售"')

        input("\n按 Enter 关闭浏览器并退出…")
        await ctx.close()


def main():
    parser = argparse.ArgumentParser(description="大泉州人才网登录助手")
    parser.add_argument("--mode", choices=["job", "resume"], default="resume",
                        help="登录后跳转到哪个页面（job=职位列表，resume=简历列表）")
    args = parser.parse_args()

    target = RESUME_LIST_URL if args.mode == "resume" else JOB_LIST_URL
    asyncio.run(do_login(target))


if __name__ == "__main__":
    main()
