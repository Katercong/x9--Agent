"""
公司线索爬虫 — 51job / 智联招聘 应聘端

用法:
  python scraper/job_platform_scraper.py --platform 51job --max-pages 5
  python scraper/job_platform_scraper.py --platform zhaopin --keywords "跨境销售,亚马逊运营"
  python scraper/job_platform_scraper.py --dry-run          # 只打印，不推送
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from urllib.request import urlopen

from platform_contract import push_all, push_one, push_talents, split_keywords

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    from playwright.async_api import async_playwright
except ImportError:
    print("[ERROR] 缺少 playwright，请执行: pip install playwright && playwright install chromium")
    sys.exit(1)


def emit_progress(phase: str, label: str, **kwargs) -> None:
    payload = {
        "phase": phase,
        "label": label,
        "current": kwargs.pop("current", 0),
        "total": kwargs.pop("total", 0),
        "current_keyword": kwargs.pop("current_keyword", ""),
        "current_page": kwargs.pop("current_page", None),
        "items_total": kwargs.pop("items_total", 0),
        **kwargs,
    }
    print("[PROGRESS] " + json.dumps(payload, ensure_ascii=False), flush=True)


def _login_policy(platform: str) -> str:
    """qzrc/51job 公司客户登录可选（采集公开信息）；智联公司客户与跨境人才平台登录必需。

    说明：智联未登录时职位详情点击会被登录墙拦截（点击不开新标签），列表页也拿不到
    可用数据，实测必须登录后才能采集，故归入登录必需口径。
    """
    return "optional" if platform in {"qzrc_job", "51job"} else "required"


# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
USER_DATA_DIR = str(ROOT / "data" / "browser-profile")
CDP_RUNTIME_PATH = ROOT / "data" / "runtime" / "chrome-cdp.json"

DEFAULT_KEYWORDS = [
    # 场景A：人才职位搜索词
    "跨境销售", "亚马逊运营", "TikTok Shop运营", "跨境电商运营",
    "海外仓招商", "外贸销售", "品牌出海", "独立站运营",
    # 场景B：公司业务方向搜索词
    "北美市场", "跨境供应链", "货代",
]

TALENT_51JOB_DEFAULT_KEYWORDS = [
    "跨境销售", "跨境电商运营", "Amazon运营", "美区运营",
    "海外仓招商", "跨境供应链", "品牌出海销售",
]

FILTER_KEYWORDS = [
    "跨境", "亚马逊", "tiktok", "tiktok shop", "海外", "外贸", "出口",
    "供应链", "海外仓", "独立站", "fba", "fbt", "shopify", "北美", "美区",
    "temu", "shein", "货代", "一件代发", "小单快反", "柔性供应链",
    "品牌出海", "品牌销售", "跨境电商",
]

EXCLUDE_COMPANY_KEYWORDS = [
    "人才网", "招聘网", "招聘平台", "人力资源", "劳务派遣", "猎头",
    "职业培训", "培训学校", "求职", "简历",
    # 贵司自有/关联公司：自家公司不采集（来源：用户明确要求“后续不要爬取自家公司数据”）
    "蓝蜻蜓", "福建蓝蜻蜓护理用品",
]

JOB51_SEARCH = "https://we.51job.com/pc/search?keyword={kw}&searchType=2&keywordType=&pageNum={page}"
JOB51_TALENT_SEARCH = "https://ehire.51job.com/Revision/talent/search?rt={ts}"
ZHAOPIN_SEARCH = "https://sou.zhaopin.com/?jl=801&kw={kw}&p={page}"
# 前程无忧公司列表翻页器 ul（用户提供的绝对 XPath）；点击式翻页优先在该范围内点页码/下一页。
JOB51_COMPANY_PAGER_UL = "xpath=/html/body/div/div/div[2]/div/div/div[2]/div[1]/div/div[2]/div/div[3]/div/div/div/ul"
# 智联人才翻页器容器（用户提供的绝对 XPath）。
ZHAOPIN_TALENT_PAGER = "xpath=/html/body/div[1]/div[2]/div[1]/div/div[1]/div[5]/div[3]/div[2]"
# 智联招聘 RD 端（招聘端）搜索人才 —— 需要企业会员登录。
# 旧的 /cvsearch/all 已在 2026-05-27 实测跳 404；当前可达入口是 /app/search。
# 为避免路由参数失效，智联人才统一模拟人工：打开搜索页 -> 输入关键词 -> 点击搜索。
ZHAOPIN_RESUME_HOME = "https://rd6.zhaopin.com/app/search"
# ---------------------------------------------------------------------------


class BrowserSessionError(RuntimeError):
    pass


def _cdp_version_url(cdp_url: str) -> str:
    return cdp_url.rstrip("/") + "/json/version"


def _is_cdp_ready(cdp_url: str) -> bool:
    try:
        with urlopen(_cdp_version_url(cdp_url), timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def _find_chrome_executable() -> str:
    candidates = [
        os.environ.get("COMPANYLEADS_CHROME_PATH", ""),
        os.environ.get("QCWY_CHROME_PATH", ""),
        os.environ.get("CHROME_PATH", ""),
        shutil.which("chrome") or "",
        shutil.which("chrome.exe") or "",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _cdp_port_from_url(cdp_url: str) -> int:
    parsed = urlparse(cdp_url)
    if parsed.port:
        return parsed.port
    return 9222


def _runtime_cdp_url() -> str:
    if not CDP_RUNTIME_PATH.exists():
        return ""

    try:
        data = json.loads(CDP_RUNTIME_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""

    url = data.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()

    port = data.get("port")
    if port:
        return f"http://127.0.0.1:{port}"
    return ""


async def _ensure_chrome_cdp(cdp_url: str) -> None:
    if _is_cdp_ready(cdp_url):
        return

    chrome = _find_chrome_executable()
    if not chrome:
        raise BrowserSessionError(
            "Chrome executable was not found. Set COMPANYLEADS_CHROME_PATH or QCWY_CHROME_PATH and retry."
        )

    port = _cdp_port_from_url(cdp_url)
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "about:blank",
    ]
    user_data_dir = (
        os.environ.get("COMPANYLEADS_CHROME_USER_DATA_DIR")
        or os.environ.get("QCWY_CHROME_USER_DATA_DIR")
        or str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CompanyLeads" / "chrome-profile")
    )
    if user_data_dir:
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        args.insert(1, f"--user-data-dir={user_data_dir}")

    print(f"[BROWSER] CDP port is not reachable, trying to start Chrome debug port: {cdp_url}")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

    for _ in range(20):
        if _is_cdp_ready(cdp_url):
            print(f"[BROWSER] Chrome CDP is ready: {cdp_url}")
            return
        await asyncio.sleep(0.5)

    raise BrowserSessionError(
        f"CDP was not reachable after starting Chrome: {cdp_url}. "
        "If Chrome was already open without remote debugging, close all Chrome windows and retry."
    )


async def rnd_delay(lo=1.5, hi=4.0):
    await asyncio.sleep(random.uniform(lo, hi))


def clean(el) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.strip())


def has_crossborder(texts: list[str]) -> bool:
    joined = " ".join(t for t in texts if t).lower()
    return any(kw.lower() in joined for kw in FILTER_KEYWORDS)


def is_excluded_company(company: str, texts: list[str] | None = None) -> bool:
    joined = " ".join([company, *(texts or [])]).lower()
    return any(kw.lower() in joined for kw in EXCLUDE_COMPANY_KEYWORDS)


def extract_contacts(text: str) -> dict[str, str]:
    text = clean(text)
    result: dict[str, str] = {}

    emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    if emails:
        result["contact_email"] = emails[0]

    phones = re.findall(r"(?:1[3-9]\d{9}|0\d{2,4}[-\s]?\d{6,8})", text)
    if phones:
        result["contact_phone"] = " / ".join(dict.fromkeys(p.replace(" ", "") for p in phones[:3]))

    same_wechat = re.search(
        r"(1[3-9]\d{9})[^。；;，,\n]{0,12}(?:微信同号|微信同手机号|同微信|手机号同微信)",
        text,
    )
    if same_wechat:
        result["hr_wechat"] = same_wechat.group(1)
    elif phones and re.search(r"微信同号|微信同手机号|同微信|手机号同微信", text):
        result["hr_wechat"] = phones[0].replace(" ", "")

    wechat_m = re.search(r"(?:微信|微信号|VX|WeChat)[：:\s]*([A-Za-z0-9_-]{5,30})", text, re.I)
    if wechat_m and not result.get("hr_wechat"):
        result["hr_wechat"] = wechat_m.group(1)

    return result


def extract_zhaopin_company_id(*values: str) -> str:
    joined = " ".join(v or "" for v in values)
    for pattern in (
        r"(?:companyId|company_id|companyNumber|comId)[=/:\s]+([A-Za-z0-9_-]{4,})",
        r"/companydetail/([A-Za-z0-9_-]+)",
        r"\b(CZ\d{5,}|CC\d{5,}|C\d{6,})\b",
    ):
        m = re.search(pattern, joined, re.I)
        if m:
            return m.group(1)
    return ""


async def first_text(root, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            el = await root.query_selector(sel)
            if el:
                txt = clean(await el.inner_text())
                if txt:
                    return txt
        except Exception:
            continue
    return ""


async def first_attr(root, selectors: list[str], attr: str) -> str:
    for sel in selectors:
        try:
            el = await root.query_selector(sel)
            if el:
                val = await el.get_attribute(attr)
                if val:
                    return val
        except Exception:
            continue
    return ""


async def check_captcha(page) -> bool:
    if page.is_closed():
        return False
    # 经典验证码组件
    for sel in ["div.nc-container", "div.geetest_panel", "iframe[src*='captcha']", "div.verify-main"]:
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            return False
    return False


# Tencent EdgeOne / Cloudflare 等"安全验证"中转页关键字
_SECURITY_PAGE_TOKENS = (
    "Security Verification",
    "正在验证连接安全性",
    "EdgeOne",
    "Cloudflare",
    "Please verify you are a human",
    "Just a moment",
    "请完成安全验证",
)


async def check_security_page(page) -> tuple[bool, str]:
    """识别 EdgeOne / Cloudflare 类安全验证中转页。返回 (是否命中, 命中关键字)。"""
    if page.is_closed():
        return False, ""
    try:
        title = (await page.title()) or ""
    except Exception:
        title = ""
    for tok in _SECURITY_PAGE_TOKENS:
        if tok.lower() in title.lower():
            return True, tok
    try:
        body = await page.evaluate(
            "() => (document.body && document.body.innerText || '').slice(0, 600)"
        )
    except Exception:
        body = ""
    body = body or ""
    for tok in _SECURITY_PAGE_TOKENS:
        if tok in body:
            return True, tok
    return False, ""


async def wait_captcha(page, timeout=180) -> bool:
    """等用户手动通过验证码 / 安全验证页。两类页面合并轮询。"""
    print("[CAPTCHA] 检测到验证码 / 安全验证，请在浏览器窗口手动完成…")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.is_closed():
            print("[CAPTCHA] 浏览器页面已关闭，中止当前任务。")
            return False
        sec_hit, _ = await check_security_page(page)
        if not await check_captcha(page) and not sec_hit:
            print("[CAPTCHA] 已通过，继续采集。")
            return True
        await asyncio.sleep(2)
    print(f"[CAPTCHA] {timeout} 秒内未通过，跳过当前页面。")
    return False


def _looks_like_domain_or_noise(value: str) -> bool:
    """识别"误抓"的常见噪声值：纯域名 / 仅 www / 全英文站点名等。"""
    if not value:
        return True
    v = value.strip().lower()
    if not v:
        return True
    if v in ("www.zhaopin.com", "zhaopin.com", "www.51job.com", "51job.com", "www.qzrc.com", "qzrc.com"):
        return True
    if v.startswith("www.") or v.endswith(".com") or v.endswith(".cn"):
        return True
    return False


# ---------------------------------------------------------------------------
# 51job
# ---------------------------------------------------------------------------

def extract_51job_company_id(*values: str) -> str:
    joined = " ".join(v or "" for v in values)
    for pattern in (
        r"/co([A-Za-z0-9._-]+)\.html",
        r"(?:companyId|coid|company_id)[=/:\s]+([A-Za-z0-9._-]{4,})",
    ):
        m = re.search(pattern, joined, re.I)
        if m:
            return m.group(1)
    return ""


def normalize_51job_company_name(value: str) -> str:
    value = clean(value)
    m = re.match(
        r"(.{2,90}?(?:有限责任公司|股份有限公司|股份公司|有限公司|集团|工厂|服装厂|商行|工作室|中心|店|事务所|分公司)(?:（个体工商户）)?)",
        value,
    )
    return clean(m.group(1)) if m else value


def parse_51job_company_meta(value: str) -> dict[str, str]:
    value = clean(value)
    out: dict[str, str] = {}
    size_m = re.search(r"少于50人|50-150人|150-500人|500-1000人|1000-5000人|5000-10000人|10000人以上", value)
    if size_m:
        out["size_range"] = size_m.group(0)
    nature_m = re.search(r"(?:民营|国企|外资|合资|上市公司|创业公司|事业单位|非营利组织)", value)
    company_name = normalize_51job_company_name(value)
    left = value.replace(company_name, "", 1)
    if nature_m:
        left = left.replace(nature_m.group(0), " ")
    if size_m:
        left = left.replace(size_m.group(0), " ")
    industry = clean(left.strip("丨|｜/ "))
    if industry and len(industry) <= 120:
        out["industry"] = industry
    return out


def _extract_51job_section(text: str, start_label: str, end_labels: list[str]) -> str:
    start = text.find(start_label)
    if start < 0:
        return ""
    content_start = start + len(start_label)
    ends = [text.find(label, content_start) for label in end_labels]
    ends = [idx for idx in ends if idx >= 0]
    end = min(ends) if ends else len(text)
    return clean(text[content_start:end])


def _set_if_better(entry: dict, key: str, value: str, limit: int = 2000) -> None:
    value = clean(value)[:limit]
    if not value:
        return
    current = clean(str(entry.get(key) or ""))
    if current and not _looks_like_domain_or_noise(current):
        return
    if _looks_like_domain_or_noise(value):
        return
    entry[key] = value


def _extract_public_contacts_51job(text: str) -> dict[str, str]:
    text = clean(text)
    contacts: dict[str, str] = {}

    name_m = re.search(r"(?:联系人|招聘联系人|HR)[:：\s]+([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z·]{1,20})", text)
    if name_m:
        contacts["contact_name"] = name_m.group(1)

    emails = re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    if emails:
        contacts["contact_email"] = emails[0]

    landlines = re.findall(r"0\d{2,4}[-\s]?\d{6,8}", text)
    mobiles: list[str] = []
    for m in re.finditer(r"1[3-9]\d{9}", text):
        window = text[max(0, m.start() - 24):m.end() + 24]
        if re.search(r"联系电话|电话|手机|联系|HR|招聘", window):
            mobiles.append(m.group(0))
    phones = [p.replace(" ", "") for p in [*landlines, *mobiles]]
    if phones:
        contacts["contact_phone"] = " / ".join(dict.fromkeys(phones[:3]))

    wx_m = re.search(r"(?:微信|微信号|VX|WeChat)[:：\s]*([A-Za-z0-9_-]{5,30})", text, re.I)
    if wx_m:
        contacts["hr_wechat"] = wx_m.group(1)
    return contacts


async def _is_51job_blocked(page) -> tuple[bool, str]:
    sec_hit, token = await check_security_page(page)
    if sec_hit:
        return True, f"security:{token}"
    if await check_captcha(page):
        return True, "captcha"
    url = page.url.lower()
    # 仅当地址跳转到登录域名时才确定为登录墙。
    if "login.51job.com" in url:
        return True, "login"
    # 列表页本身常带"登录/注册"头部按钮，不能用裸"登录"判断登录墙，
    # 否则会把正常的第 2 页等误判为登录墙 -> 返回空 -> 翻页提前中断（仅采到约 15 条）。
    # 只有在出现登录专用提示语、且页面没有任何职位卡片时，才视为登录墙。
    try:
        has_cards = await page.evaluate(
            "() => !!document.querySelector('.joblist-item, div.e a.el, div.joblist-box__item')"
        )
    except Exception:
        has_cards = False
    if has_cards:
        return False, ""
    try:
        body = await page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        body = ""
    head = body[:800]
    login_phrases = ("扫码登录", "账号登录", "请登录", "登录后查看", "登录查看", "立即登录", "登录后才能")
    if any(p in head for p in login_phrases):
        return True, "login"
    return False, ""


async def _scroll_to_load_more(page, rounds: int = 8, pause_lo: float = 0.8,
                               pause_hi: float = 1.6) -> bool:
    """向下滚动触发懒加载 / 下拉刷新，加载更多列表项。

    返回是否检测到页面高度增长（即“可能加载了更多”）。高度连续两轮不再增长则提前停止。
    适用于“下拉刷新出新数据”的列表（如前程无忧人才、大泉州人才）。
    """
    grew = False
    last_height = -1
    stagnant = 0
    for _ in range(max(1, rounds)):
        try:
            await page.mouse.wheel(0, 2400)
        except Exception:
            try:
                await page.evaluate("() => window.scrollBy(0, document.body.scrollHeight)")
            except Exception:
                pass
        await rnd_delay(pause_lo, pause_hi)
        try:
            height = await page.evaluate(
                "() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
        except Exception:
            height = 0
        if height and height > last_height:
            grew = True
            stagnant = 0
        else:
            stagnant += 1
            if stagnant >= 2:
                break
        last_height = height
    return grew


async def _goto_51job_company_page(page, pg: int) -> bool:
    """前程无忧公司列表点击式翻页（仿照 qzrc/zhaopin）：在翻页器 ul 内点击目标页码 / 下一页。

    仅在 pg>1 时调用。点击后等待列表首张卡片文本变化以确认翻页生效。
    成功返回 True；找不到可点击的翻页控件（通常已到末页）返回 False。
    """
    if pg <= 1:
        return True
    try:
        before = await page.locator(".joblist-item").first.inner_text(timeout=1500)
    except Exception:
        before = ""

    candidates = []
    pager = page.locator(JOB51_COMPANY_PAGER_UL).first
    try:
        if await pager.count() > 0:
            for sub in (f"li:text-is('{pg}')", f"a:text-is('{pg}')", f"button:text-is('{pg}')",
                        "li.number:has-text('下一页')", "li:has-text('下一页')",
                        "li.next", "a.next", ".btn-next"):
                candidates.append(pager.locator(sub).first)
    except Exception:
        pass
    # 全页兜底：页码文本 / 通用下一页按钮
    for sel in (f"li:text-is('{pg}')", f"a:text-is('{pg}')", f"button:text-is('{pg}')",
                ".el-pagination .btn-next", "button.btn-next", ".btn-next",
                ".pagination-next", "li.next", "a.next",
                "button:has-text('下一页')", "a:has-text('下一页')"):
        candidates.append(page.locator(sel).first)

    for target in candidates:
        try:
            if await target.count() == 0 or not await target.is_visible(timeout=400):
                continue
            cls = (await target.get_attribute("class")) or ""
            aria = await target.get_attribute("aria-disabled")
            if aria == "true" or re.search(r"disabled|is-disabled", cls):
                continue
            await target.scroll_into_view_if_needed()
            await target.hover()
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await target.click(timeout=4000)
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    after = await page.locator(".joblist-item").first.inner_text(timeout=1000)
                except Exception:
                    after = ""
                if after and after != before:
                    return True
                await asyncio.sleep(0.6)
            # 点过了但没检测到明显变化，交给上层的“翻页未推进”去重逻辑判定
            return True
        except Exception:
            continue
    return False


async def scrape_51job_page(page, keyword: str, pg: int, captcha_timeout: int,
                            inspect: bool = False, delay_min: float = 2.0,
                            delay_max: float = 4.0) -> list[dict]:
    if pg <= 1:
        url = JOB51_SEARCH.format(kw=quote(keyword), page=1)
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await rnd_delay(delay_min, delay_max)
    else:
        # 点击式翻页：在当前列表页点击翻页器，不再用 URL 直接跳转（修复 URL 翻页跳到末页的问题）。
        if not await _goto_51job_company_page(page, pg):
            print(f"[51JOB] 未找到可点击的翻页控件（第 {pg} 页，通常已到末页），停止当前关键词")
            return []
        await rnd_delay(delay_min, delay_max)
    url = page.url
    blocked, reason = await _is_51job_blocked(page)
    if blocked:
        if reason == "captcha":
            if not await wait_captcha(page, captcha_timeout):
                return []
        elif reason == "login":
            # 公司客户口径：登录可选。不再等待人工登录，仅记录并跳过当前页，保留已采集公开信息。
            print(f"[LOGIN-OPTIONAL] 51job 公司搜索列表需要登录，仅采集公开信息、不强制登录，跳过当前页: {page.url}")
            return []
        else:
            print(f"[51JOB] 列表页被拦截，跳过当前页: {reason} {page.url}")
            return []

    try:
        await page.wait_for_selector(".joblist-item, div.e a.el, div.joblist-box__item", timeout=15_000)
    except Exception:
        pass

    cards = await page.query_selector_all(".joblist-item")

    results = []
    for index, card in enumerate(cards):
        try:
            data = await card.evaluate("""(item) => {
                const text = (node) => (node && node.innerText || '').replace(/\\s+/g, ' ').trim();
                const attr = (node, name) => node ? (node.getAttribute(name) || '') : '';
                const pick = (selectors) => {
                  for (const sel of selectors) {
                    const el = item.querySelector(sel);
                    if (el && text(el)) return text(el);
                  }
                  return '';
                };
                const pickHref = (selectors) => {
                  for (const sel of selectors) {
                    const el = item.querySelector(sel);
                    const href = attr(el, 'href');
                    if (href) return href;
                  }
                  return '';
                };
                const companyLink = item.querySelector('.joblist-item-right a.comp, a.comp');
                const titleLink = item.querySelector(
                  'a.jname, a[class*="job-title"], a[href*="jobs.51job.com"]:not(.comp), a[href*="/p"]:not(.comp)'
                );
                return {
                  card_text: text(item).slice(0, 1800),
                  company_name: text(companyLink) || pick(['[class*="company"] a', '[class*="company"]']),
                  company_url: attr(companyLink, 'href'),
                  jd_title: text(titleLink) || pick(['[class*="jname"]', '[class*="job-title"]', '[class*="title"]']),
                  job_url: attr(titleLink, 'href'),
                  city: pick(['[class*="area"]', '[class*="city"]', '.job-area']),
                  salary_range: pick(['[class*="salary"]', '.sal', '.salary']),
                  meta: pick(['.joblist-item-right', '[class*="company"]'])
                };
            }""")
            jd_title = clean(data.get("jd_title") or "")
            company_raw = clean(data.get("company_name") or "")
            company = normalize_51job_company_name(company_raw)
            card_text = clean(data.get("card_text") or "")
            if not company:
                m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9（）()·]{4,80}(?:公司|集团|工厂|商行|工作室|中心|店))", card_text)
                company = clean(m.group(1)) if m else ""
            if not company or is_excluded_company(company, [jd_title, card_text[:500]]):
                continue
            jd_url = urljoin(page.url, data.get("job_url") or "")
            company_url = urljoin(page.url, data.get("company_url") or "")
            source_url = prefer_detail_url(jd_url, company_url, page.url)
            company_id = extract_51job_company_id(company_url, jd_url, card_text)
            city = clean(data.get("city") or "")
            salary = clean(data.get("salary_range") or "")
            meta = parse_51job_company_meta(company_raw)
            raw_data = {
                "keyword": keyword,
                "page": pg,
                "card_index": index,
                "search_url": url,
                "company_url": company_url,
                "job_url": jd_url,
                "card_text": card_text,
                "company_text_raw": company_raw,
            }
            if inspect and index < 3:
                print(f"[INSPECT-51JOB] card={index} company={company!r} title={jd_title!r} company_url={company_url}")
            results.append({
                "platform": "51job",
                "platform_company_id": company_id,
                "company_name": company,
                "jd_title": jd_title,
                "city": city,
                "salary_range": salary,
                "industry": meta.get("industry", ""),
                "size_range": meta.get("size_range", ""),
                "source_url": source_url,
                "source_mode": "job_seeker",
                "raw_data": raw_data,
            })
        except Exception:
            continue

    if not results:
        # 旧版搜索页兜底，保留框架里原有路径。
        links = await page.query_selector_all("div.e a.el, div.joblist-box__item a")
        for index, link in enumerate(links):
            try:
                jd_title = clean(await link.inner_text())
                jd_url = await link.get_attribute("href") or ""
                row = await link.evaluate_handle("el => el.closest('tr') || el.parentElement")
                cells = await row.query_selector_all("td")
                company = clean(await cells[1].inner_text()) if len(cells) > 1 else ""
                city = clean(await cells[2].inner_text()) if len(cells) > 2 else ""
                if not company or is_excluded_company(company, [jd_title]):
                    continue
                results.append({
                    "platform": "51job",
                    "platform_company_id": extract_51job_company_id(jd_url),
                    "company_name": company,
                    "jd_title": jd_title,
                    "city": city,
                    "source_url": prefer_detail_url(urljoin(page.url, jd_url), page.url),
                    "source_mode": "job_seeker",
                    "raw_data": {"keyword": keyword, "page": pg, "card_index": index, "search_url": url, "job_url": jd_url},
                })
            except Exception:
                continue
    return results


async def _open_51job_detail_by_click(list_page, entry: dict, target_url: str, kind: str,
                                      captcha_timeout: int, delay_min: float, delay_max: float,
                                      timeout_ms: int = 15_000):
    raw = entry.setdefault("raw_data", {})
    if not isinstance(raw, dict):
        raw = {"raw": raw}
        entry["raw_data"] = raw
    if not target_url:
        return None, "missing_url"

    payload = {
        "targetUrl": target_url,
        "kind": kind,
        "cardIndex": raw.get("card_index"),
    }
    click_target = await list_page.evaluate(
        """({ targetUrl, kind, cardIndex }) => {
          const abs = (href) => {
            try { return new URL(href, location.href).href; } catch { return href || ''; }
          };
          const canon = (href) => abs(href).replace(/[?#].*$/, '').replace(/\\/$/, '');
          const targetCanon = canon(targetUrl);
          const visible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
          };
          const byHref = Array.from(document.querySelectorAll('a[href]')).find((a) => (
            visible(a) && (canon(a.getAttribute('href')) === targetCanon || canon(a.href) === targetCanon)
          ));
          const cards = Array.from(document.querySelectorAll('.joblist-item, div.e, div.joblist-box__item'));
          const card = Number.isInteger(cardIndex) ? cards[cardIndex] : null;
          const selectors = kind === 'company'
            ? ['.joblist-item-right a.comp', 'a.comp', "a[href*='/co'][href*='.html']", "a[href*='company']"]
            : ['a.jname', "a[class*='job-title']", "a[href*='jobs.51job.com']:not(.comp)", "a[href*='/p']:not(.comp)", 'a[href]'];
          let anchor = byHref;
          if (!anchor && card) {
            for (const sel of selectors) {
              const found = card.querySelector(sel);
              if (found && visible(found)) { anchor = found; break; }
            }
          }
          if (!anchor) {
            return { ok: false, reason: 'anchor_not_found', kind, targetUrl, cardIndex, anchor_count: document.querySelectorAll('a[href]').length };
          }
          anchor.scrollIntoView({ block: 'center', inline: 'center' });
          anchor.setAttribute('target', '_blank');
          anchor.setAttribute('rel', 'noopener');
          const rect = anchor.getBoundingClientRect();
          if (!rect.width || !rect.height) {
            return { ok: false, reason: 'anchor_not_visible', kind, href: anchor.href || anchor.getAttribute('href') || '' };
          }
          return {
            ok: true,
            x: Math.round(rect.left + rect.width / 2),
            y: Math.round(rect.top + rect.height / 2),
            href: anchor.href || anchor.getAttribute('href') || '',
            kind,
          };
        }""",
        payload,
    )
    if not click_target.get("ok"):
        raw[f"{kind}_click_skipped_reason"] = click_target.get("reason") or "anchor_not_found"
        raw[f"{kind}_click_debug"] = click_target
        return None, raw[f"{kind}_click_skipped_reason"]

    detail_page = None
    try:
        await list_page.bring_to_front()
        await list_page.mouse.move(click_target["x"], click_target["y"])
        await asyncio.sleep(random.uniform(0.2, 0.5))
        async with list_page.expect_popup(timeout=timeout_ms) as popup_info:
            await list_page.mouse.click(click_target["x"], click_target["y"])
        detail_page = await popup_info.value
    except PlaywrightTimeoutError:
        raw[f"{kind}_click_skipped_reason"] = "new_tab_timeout"
        raw[f"{kind}_click_debug"] = click_target
        return None, "new_tab_timeout"

    try:
        await detail_page.wait_for_load_state("domcontentloaded", timeout=25_000)
    except Exception:
        pass
    await rnd_delay(delay_min, delay_max)
    blocked, reason = await _is_51job_blocked(detail_page)
    if not blocked:
        return detail_page, ""
    # 纯登录墙：公司客户口径下登录可选，跳过该详情、保留列表公开字段，不停整批。
    if reason == "login":
        raw[f"{kind}_login_reason"] = reason
        return None, "login_wall"
    # 命中反爬验证（验证码/安全验证）：不自动绕过 / 不模拟滑块 / 不自动重试；保留验证页给人工，
    # 不关闭，返回 verify_hold 通知上层立即停止本轮任务。
    raw[f"{kind}_verify_reason"] = reason
    return None, "verify_hold"


def _canonical_51job_url(url: str) -> str:
    """规范化 51job 详情 URL 作为缓存 key：去掉 query/hash 与结尾斜杠。

    规则与 _open_51job_detail_by_click 内 JS 的 canon() 保持一致，
    确保缓存 key 与点击目标匹配。
    """
    if not url:
        return ""
    return re.sub(r"[?#].*$", "", url.strip()).rstrip("/")


async def enrich_51job(page, entry: dict, captcha_timeout: int = 60,
                       delay_min: float = 1.5, delay_max: float = 3.0) -> dict:
    raw = entry.setdefault("raw_data", {})
    if not isinstance(raw, dict):
        raw = {"raw": raw}
        entry["raw_data"] = raw

    job_url = entry.get("source_url", "")
    company_url = raw.get("company_url", "")
    company_click_page = page
    job_detail_page = None

    # 本轮（单个 entry）内由脚本打开的详情页：canonical url -> page
    opened_pages: dict = {}
    opened_order: list = []

    async def _get_or_open(click_from_page, target_url, kind):
        """打开详情页；若本轮已打开同一 canonical URL，复用已有 page，不再 click。"""
        canon = _canonical_51job_url(target_url)
        if not canon:
            return None, "missing_url"
        cached = opened_pages.get(canon)
        if cached is not None and not cached.is_closed():
            raw[f"{kind}_detail_reused"] = True
            print(f"[51JOB-REUSE] kind={kind} url={canon}")
            return cached, ""
        if cached is not None:
            opened_pages.pop(canon, None)
        print(f"[51JOB-OPEN] kind={kind} url={canon}")
        detail, reason = await _open_51job_detail_by_click(
            click_from_page, entry, target_url, kind, captcha_timeout, delay_min, delay_max
        )
        if reason == "login_wall":
            # 公司客户口径：详情登录可选。仅跳过该详情、标记 login_wall_hit，保留列表公开字段，不停整批。
            raw["login_wall_hit"] = True
            raw[f"{kind}_login_wall"] = True
            print(f"[LOGIN-OPTIONAL] kind={kind} url={canon} 详情需要登录，跳过该详情并保留公开信息，不停整批")
            return None, reason
        if reason == "verify_hold":
            raw["job51_verify_hold"] = True
            print(f"[51JOB-VERIFY-HOLD] kind={kind} url={canon} 命中反爬验证，停止本轮并保留验证页")
            return None, reason
        if detail is not None:
            opened_pages[canon] = detail
            opened_order.append(detail)
            raw[f"{kind}_detail_opened_once"] = True
        return detail, reason

    if job_url and job_url.startswith("http") and "jobs.51job.com" in job_url:
        try:
            detail, reason = await _get_or_open(page, job_url, "job")
            if not detail:
                raw["job_enrich_skipped_reason"] = reason
            else:
                job_detail_page = detail
                body_text = clean(await detail.evaluate("() => document.body ? document.body.innerText : ''"))
                raw["job_detail_url"] = detail.url
                raw["job_detail_text"] = body_text[:3000]

                title = await first_text(detail, ["h1", ".job-title", "[class*='job-title']", "[class*='title']"])
                _set_if_better(entry, "jd_title", title, 300)

                salary = await first_text(detail, [".salary", "[class*='salary']", ".job_msg"])
                _set_if_better(entry, "salary_range", salary, 120)

                jd_desc = ""
                for sel in ["div.job-detail", ".job-detail", ".bmsg.job_msg", "[class*='job-detail']", "[class*='description']"]:
                    el = await detail.query_selector(sel)
                    if el:
                        txt = clean(await el.inner_text())
                        if len(txt) > 20:
                            jd_desc = txt
                            break
                if not jd_desc:
                    jd_desc = _extract_51job_section(body_text, "职位信息", ["职能类别", "联系方式", "公司信息", "公司简介"])
                _set_if_better(entry, "jd_description", jd_desc, 2500)

                info = await first_text(detail, ["p.msg.ltype", ".com_tag", "[class*='company'] [class*='tag']"])
                parts = [clean(s) for s in re.split(r"[|｜]", info) if clean(s)]
                if parts:
                    for part in parts:
                        if not entry.get("city") and re.search(r"[\u4e00-\u9fa5]{2,8}", part):
                            entry["city"] = part[:100]
                        elif not entry.get("industry") and len(part) <= 80:
                            entry["industry"] = part
                        elif not entry.get("size_range") and re.search(r"人|少于|以上", part):
                            entry["size_range"] = part

                for key, value in _extract_public_contacts_51job(jd_desc).items():
                    _set_if_better(entry, key, value, 320)

                if not company_url:
                    company_url = await first_attr(detail, ["a[href*='/co'][href*='.html']", "a.company-name"], "href")
                    company_url = urljoin(detail.url, company_url) if company_url else ""
                    raw["company_url"] = company_url
                    company_click_page = detail
        except Exception as exc:
            raw["job_enrich_error"] = str(exc)[:300]

    if company_url and company_url.startswith("http") and not raw.get("job51_verify_hold"):
        try:
            detail, reason = await _get_or_open(company_click_page, company_url, "company")
            # fallback：仅当未拿到可用 page 时才换页面源重试；
            # 若该 URL 已在本轮打开过，跳过重复点击、直接复用。
            if not detail:
                canon = _canonical_51job_url(company_url)
                cached = opened_pages.get(canon)
                if cached is not None and not cached.is_closed():
                    raw["company_detail_reused"] = True
                    print(f"[51JOB-SKIP-DUP] kind=company url={canon}")
                    detail, reason = cached, ""
                else:
                    for alt in (page, job_detail_page):
                        if alt is None or alt is company_click_page or alt.is_closed():
                            continue
                        detail, reason = await _get_or_open(alt, company_url, "company")
                        if detail:
                            break
            if not detail:
                raw["company_enrich_skipped_reason"] = reason
            else:
                try:
                    body_text = clean(await detail.evaluate("() => document.body ? document.body.innerText : ''"))
                    raw["company_detail_url"] = detail.url
                    raw["company_detail_text"] = body_text[:3500]
                    company_id = extract_51job_company_id(detail.url, company_url)
                    if company_id and not entry.get("platform_company_id"):
                        entry["platform_company_id"] = company_id

                    name = await first_text(detail, [
                        "xpath=/html/body/div/div/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div[2]/div[1]/h1",
                        "h1", ".company-name", "[class*='company-name']",
                    ])
                    _set_if_better(entry, "company_name", name, 300)

                    nature = await first_text(detail, ["xpath=/html/body/div/div/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div[2]/div[2]/span[1]"])
                    size = await first_text(detail, ["xpath=/html/body/div/div/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div[2]/div[2]/span[2]"])
                    industry = await first_text(detail, ["xpath=/html/body/div/div/div/div/div/div[2]/div[1]/div[1]/div/div[1]/div[2]/div[2]/span[3]"])
                    _set_if_better(entry, "size_range", size, 120)
                    _set_if_better(entry, "industry", industry, 200)
                    if nature:
                        raw["company_nature"] = nature

                    intro = await first_text(detail, [
                        "xpath=/html/body/div/div/div/div/div/div[2]/div[2]/div[1]/div[1]/div[1]/div[1]",
                        ".company-intro", ".company-detail", "[class*='company'] [class*='intro']",
                    ])
                    if not intro:
                        intro = _extract_51job_section(body_text, "公司介绍", ["在招职位", "公司地址", "工商信息"])
                    _set_if_better(entry, "company_description", intro, 2500)

                    address = await first_text(detail, [
                        "xpath=/html/body/div/div/div/div/div/div[2]/div[2]/div[1]/div[2]/div[2]/div[1]/div[2]/div",
                        ".company-address", "[class*='address']",
                    ])
                    if not address:
                        address = _extract_51job_section(body_text, "公司地址", ["工商信息", "热门城市", "推荐职位"])
                    _set_if_better(entry, "company_address", address.replace("查看地图", " "), 500)

                    if not entry.get("industry") or not entry.get("size_range"):
                        header = clean(body_text.split("屏蔽该公司")[0] if "屏蔽该公司" in body_text else body_text[:500])
                        size_m = re.search(r"少于50人|50-150人|150-500人|500-1000人|1000-5000人|5000-10000人|10000人以上", header)
                        if size_m:
                            _set_if_better(entry, "size_range", size_m.group(0), 120)
                        if not entry.get("industry"):
                            for token in re.split(r"\s+", header):
                                if 2 <= len(token) <= 40 and token not in (entry.get("company_name") or ""):
                                    if any(k in token for k in ("电商", "贸易", "物流", "互联网", "供应链", "服装", "电子")):
                                        entry["industry"] = token
                                        break

                    contact_scope = " ".join([intro, address])
                    for key, value in _extract_public_contacts_51job(contact_scope).items():
                        _set_if_better(entry, key, value, 320)
                finally:
                    # 详情页不在此关闭，统一由本轮结束时按 opened_order 清理
                    pass
        except Exception as exc:
            raw["company_enrich_error"] = str(exc)[:300]
    elif raw.get("job51_verify_hold"):
        raw["company_enrich_skipped_reason"] = "verify_hold"
    else:
        raw["company_enrich_skipped_reason"] = "missing_company_url"

    # 统一清理：关闭本轮由脚本打开的所有详情页（job + company），
    # 保留搜索列表页（page）与用户手动打开的页面。
    for opened in opened_order:
        if opened is None or opened is page:
            continue
        if not opened.is_closed():
            try:
                await opened.close()
            except Exception:
                pass

    try:
        entry["raw_data"] = raw
    except Exception:
        pass
    return entry


# ---------------------------------------------------------------------------
# Zhaopin
# ---------------------------------------------------------------------------

_ZHAOPIN_DETAIL_URL_RE = re.compile(
    # 匹配两类：
    #   ① jobs.zhaopin.com/<anything>.htm  （旧版/新版 detail 直挂 jobs 子域）
    #   ② www.zhaopin.com/(job|jobdetail|position|product/position)/<id>
    r"https?://(?:jobs?\.zhaopin\.com/[A-Za-z0-9_-]+\.html?"
    r"|(?:www\.|m\.)?zhaopin\.com/(?:jobdetail|job|position|product/position)s?/[A-Za-z0-9_/-]+)",
    re.IGNORECASE,
)
_ZHAOPIN_CITY_KEYS = (
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "西安",
    "苏州", "天津", "厦门", "福州", "泉州", "宁波", "东莞", "佛山", "青岛", "大连",
    "沈阳", "长沙", "郑州", "合肥", "昆明", "南昌", "贵阳", "兰州", "石家庄", "海口",
)
_SALARY_RE = re.compile(r"\d+[Kk-]+\d*[Kk]?(?:/月|/年|·\d+薪)?|\d+万-?\d*万?(?:/年)?")
_EXP_RE = re.compile(r"(\d+-?\d*年|应届|经验不限|不限经验|在校|实习)")
_EDU_RE = re.compile(r"(博士|硕士|本科|大专|高中|中专|学历不限)")


async def _zhaopin_login_state(page) -> tuple[bool, str]:
    """Return (logged_in, reason) for the public Zhaopin search page."""
    if page.is_closed():
        return False, "page_closed"
    try:
        return await page.evaluate(
            """() => {
              const clean = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
              const text = clean(document.body && document.body.innerText || '');
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
              };
              const nodes = Array.from(document.querySelectorAll('a,button,span,div,input')).filter(visible);
              const loginEntry = nodes.some(el => {
                const t = clean(el.innerText || el.textContent || el.getAttribute('placeholder') || '');
                return /^(登录|登录\\/注册)$/.test(t) || /验证码登录\\/注册|手机号|短信验证码|获取验证码/.test(t);
              });
              const userHint = /退出登录|账号设置|个人中心|我的简历|求职中心|投递记录|沟通过|我的投递/.test(text);
              const loginPanel = /验证码登录\\/注册|手机号|短信验证码|获取验证码/.test(text);
              if (userHint) return [true, 'user_hint'];
              if (loginPanel || loginEntry) return [false, 'login_panel'];
              return [true, 'no_login_marker'];
            }"""
        )
    except Exception as exc:
        return True, f"detect_failed:{exc}"


# 智联公司客户硬性要求登录：跨关键词只提示/等待一次，超时后置 giveup 标记，避免每个关键词都重复空等。
_zhaopin_login_required_giveup = False


async def _wait_zhaopin_login(page, timeout: int) -> bool:
    """智联公司客户必须登录：未登录时把工作窗口置前并轮询等待人工登录；超时则放弃采集。"""
    global _zhaopin_login_required_giveup
    if _zhaopin_login_required_giveup:
        return False
    logged_in, _ = await _zhaopin_login_state(page)
    if logged_in:
        return True
    try:
        await page.bring_to_front()
    except Exception:
        pass
    print(f"[LOGIN-REQUIRED] 智联公司客户必须登录后才能采集。请在打开的浏览器窗口登录智联（最多等 {timeout}s）…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(3)
        if page.is_closed():
            return False
        logged_in, _ = await _zhaopin_login_state(page)
        if logged_in:
            print("[LOGIN] 智联已登录，继续采集。")
            return True
    _zhaopin_login_required_giveup = True
    print("[LOGIN-REQUIRED] 等待超时仍未登录，已停止智联采集。请登录后重试。")
    return False


def _parse_zhaopin_card_text(text: str) -> dict[str, str]:
    """从智联卡片整段文字里抠出 title/company/city/salary 等字段（兜底）。
    智联卡片文本结构常见为：
        职位名 \n 薪资 \n 城市|经验|学历 \n 公司名 \n 行业 \n 福利标签
    """
    if not text:
        return {"card_text": ""}
    # 注意：不要先 clean()，因为它会把换行折叠掉
    raw_lines = re.split(r"[\n\r]+", text)
    lines = []
    for raw in raw_lines:
        # 在行内再切：以 2+ 空格 / 制表符 / 中点 分割成片段（但保留单空格 e.g. "3-5年 本科"）
        for piece in re.split(r"[\t]+|\s{2,}|·", raw):
            piece = piece.strip()
            if piece:
                lines.append(piece)
    flat = clean(text)
    out: dict[str, str] = {"card_text": flat[:1500]}

    # 薪资
    m = _SALARY_RE.search(flat)
    if m:
        out["salary"] = m.group(0).strip()
    # 城市
    for city in _ZHAOPIN_CITY_KEYS:
        if city in flat[:300]:
            out["city"] = city
            break
    # 经验/学历
    m_exp = _EXP_RE.search(flat)
    if m_exp:
        out["experience_hint"] = m_exp.group(1)
    m_edu = _EDU_RE.search(flat)
    if m_edu:
        out["education_hint"] = m_edu.group(1)

    # 标题：第一个不含薪资/城市/经验关键字的短行
    candidates = [l for l in lines if 2 <= len(l) <= 80]
    for l in candidates:
        if (_SALARY_RE.search(l) or _EXP_RE.search(l)
                or any(c in l for c in _ZHAOPIN_CITY_KEYS if c in l[:6])):
            continue
        out["title_candidate"] = l
        break

    # 公司：含 "公司/有限/集团" 等后缀的行
    for l in candidates:
        if l == out.get("title_candidate"):
            continue
        if re.search(r"(?:公司|有限|集团|工厂|商行|事务所|工作室|分公司|店|厂|社|机构)$", l):
            out["company_candidate"] = l
            break
    return out


# 智联公司列表卡片选择器（翻页前后对比首张卡片文本，确认翻页生效）
_ZP_COMPANY_ITEMS_SEL = (
    "li.positionlist_item, div.contentpanel-map-job, div.job-card, "
    "div[class*='joblist-box__item'], div[class*='positionlist_item'], "
    "div[class*='job-card'], div[class*='contentpile'] div[class*='item']"
)


async def _goto_zhaopin_company_page(page, pg: int) -> bool:
    """智联公司列表点击式翻页（仿照 51job / 智联人才）：点击翻页器页码或“下一页”并确认列表刷新。

    仅在 pg>1 时调用。修复智联是 SPA、URL ?p= 翻页经常被忽略而始终停留第 1 页的问题。
    点击后等待首张卡片文本变化以确认翻页生效。
    成功返回 True；找不到可点击的翻页控件（通常已到末页）返回 False。
    """
    if pg <= 1:
        return True
    try:
        before = await page.locator(_ZP_COMPANY_ITEMS_SEL).first.inner_text(timeout=1500)
    except Exception:
        before = ""

    candidates = []
    # 智联搜索经典翻页器 .soupager（含页码与“下一页”）；新版可能是 Element UI / 通用分页
    pager = page.locator(".soupager, .pagination, .el-pagination").first
    try:
        if await pager.count() > 0:
            for sub in (f"button:text-is('{pg}')", f"a:text-is('{pg}')", f"li:text-is('{pg}')",
                        ".soupager__btn--next", "button.soupager__btn--next",
                        ".el-pagination__next", "button:has-text('下一页')",
                        "a:has-text('下一页')", "[class*='next']"):
                candidates.append(pager.locator(sub).first)
    except Exception:
        pass
    # 全页兜底：页码文本 / 通用下一页按钮
    for sel in (f"button:text-is('{pg}')", f"a:text-is('{pg}')", f"li:text-is('{pg}')",
                ".soupager__btn--next", "button.soupager__btn--next",
                ".el-pagination .btn-next", "button.btn-next", ".btn-next",
                ".pagination-next", "li.next", "a.next",
                "button:has-text('下一页')", "a:has-text('下一页')"):
        candidates.append(page.locator(sel).first)

    for target in candidates:
        try:
            if await target.count() == 0 or not await target.is_visible(timeout=400):
                continue
            cls = (await target.get_attribute("class")) or ""
            aria = await target.get_attribute("aria-disabled")
            if aria == "true" or re.search(r"disabled|is-disabled", cls):
                continue
            await target.scroll_into_view_if_needed()
            await target.hover()
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await target.click(timeout=4000)
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    after = await page.locator(_ZP_COMPANY_ITEMS_SEL).first.inner_text(timeout=1000)
                except Exception:
                    after = ""
                if after and after != before:
                    return True
                await asyncio.sleep(0.6)
            # 点过了但没检测到明显变化，交给上层“翻页未推进/全部重复”去重逻辑判定
            return True
        except Exception:
            continue
    return False


async def scrape_zhaopin_page(page, keyword: str, pg: int, captcha_timeout: int,
                              inspect: bool = False) -> list[dict]:
    if pg <= 1:
        url = ZHAOPIN_SEARCH.format(kw=quote(keyword), page=1)
        await page.goto(url, timeout=30_000)
        await rnd_delay(2, 4)
    else:
        # 点击式翻页：不再用 URL ?p= 直接跳转（SPA 下经常被忽略、停留第 1 页），改为点击翻页器。
        if not await _goto_zhaopin_company_page(page, pg):
            print(f"[ZHAOPIN] 未找到可点击的翻页控件（第 {pg} 页，通常已到末页），停止当前关键词")
            return []
        await rnd_delay(2, 4)
    if await check_captcha(page):
        if not await wait_captcha(page, captcha_timeout):
            return []
    # 安全验证（EdgeOne/滑块/Cloudflare）仍需人工通过，不自动绕过。
    sec_hit, sec_token = await check_security_page(page)
    if sec_hit:
        print(f"[CAPTCHA] 智联公司搜索命中安全验证 ({sec_token})，等待人工通过…")
        if not await wait_captcha(page, captcha_timeout):
            return []
    # 公司客户硬性要求登录：未登录会被登录墙拦截详情点击、列表页也拿不到可用数据，
    # 故未登录时置前工作窗口、等待人工登录；超时仍未登录则直接放弃本页采集。
    if not await _wait_zhaopin_login(page, captcha_timeout):
        return []

    cards = await page.query_selector_all(
        "li.positionlist_item, div.contentpanel-map-job, div.job-card, "
        "div[class*='joblist-box__item'], div[class*='positionlist_item'], "
        "div[class*='job-card'], div[class*='contentpile'] div[class*='item']"
    )
    print(f"[INFO] zhaopin 找到 {len(cards)} 张卡片")
    results = []
    debug_printed = 0
    for card in cards:
        try:
            title_el = await card.query_selector(
                "a.position-title, a.jobname, a[class*='job-name'], "
                "a[class*='position-title'], a[href*='jobs.zhaopin.com'], "
                "a[href*='zhaopin.com/jobdetail'], a[href*='zhaopin.com/job/']"
            )
            company_el = await card.query_selector(
                "a.company-name, a.companyname, a[class*='company'], "
                "[class*='companyName'] a, [class*='company-name'] a"
            )
            jd_title = clean(await title_el.inner_text()) if title_el else ""
            company = clean(await company_el.inner_text()) if company_el else ""
            if len(company) > 80:
                m = re.search(r"(?:公司名称|招聘单位|企业名称)[\s:：]+([^|\n]{2,80})", clean(await card.inner_text()))
                company = clean(m.group(1)) if m else ""
            city = await first_text(card, [
                "span.work-area", "span.area", "[class*='city']", "[class*='area']",
                "[class*='job-area']", "[class*='work']",
            ])
            salary = await first_text(card, [
                "[class*='salary']", ".salary", ".job-salary", ".position-salary",
            ])
            tags = await first_text(card, [
                "[class*='tag']", "[class*='welfare']", "[class*='requirement']",
            ])
            jd_url = await title_el.get_attribute("href") if title_el else ""
            company_url = await company_el.get_attribute("href") if company_el else ""
            card_text = clean(await card.inner_text())

            # --- inspect 模式：第一张卡片打印所有 a[href]，帮你定位新版选择器 ---
            if inspect and debug_printed < 2:
                all_links = await card.query_selector_all("a[href]")
                print(f"\n[INSPECT-CARD] 卡片 {debug_printed} 含 {len(all_links)} 个 a[href]:")
                for i, a in enumerate(all_links[:12]):
                    href = await a.get_attribute("href") or ""
                    text = clean(await a.inner_text())[:40]
                    cls = await a.get_attribute("class") or ""
                    print(f"  [{i}] href={href[:120]}  class={cls[:50]}  text={text!r}")
                print(f"[INSPECT-CARD] card_text 前 400 字:\n  {card_text[:400]}\n")
                debug_printed += 1

            # --- card_text 兜底解析（CSS selector 拿不到时启用）---
            parsed = _parse_zhaopin_card_text(card_text)
            if not jd_title:
                jd_title = parsed.get("title_candidate", "")
            if not company:
                company = parsed.get("company_candidate", "")
            if not city:
                city = parsed.get("city", "")
            if not salary:
                salary = parsed.get("salary", "")
            # 从 card_text 找一个详情链接
            if not jd_url:
                m_url = _ZHAOPIN_DETAIL_URL_RE.search(card_text)
                if m_url:
                    jd_url = m_url.group(0)

            company_id = (
                await card.get_attribute("data-company-id")
                or await card.get_attribute("data-company")
                or extract_zhaopin_company_id(company_url, jd_url, card_text)
            )
            if not company or is_excluded_company(company, [jd_title, tags]):
                continue
            # Fix 2: 过滤判断不再纳入 keyword 本身（只看实际抓到的内容）
            if not has_crossborder([company, jd_title, tags, card_text[:400]]):
                continue
            # Fix 3: 没有 jd_title 或详情 URL → 不入库（避免泛岗位/空数据）
            has_detail_url = bool(jd_url and _ZHAOPIN_DETAIL_URL_RE.search(jd_url))
            if not jd_title:
                print(f"[SKIP] 智联卡片缺 jd_title: company={company[:30]}, card_text 前 80 字: {card_text[:80]}")
                continue
            if not has_detail_url:
                print(f"[SKIP] 智联卡片无职位详情 URL: {company[:30]} / {jd_title[:30]}")
                continue

            normalized_jd_url = urljoin("https://www.zhaopin.com", jd_url) if jd_url else page.url
            results.append({
                "platform": "zhaopin",
                "platform_company_id": company_id,
                "company_name": company,
                "jd_title": jd_title,
                "city": city,
                "salary_range": salary,
                "source_url": normalized_jd_url,
                "source_mode": "job_seeker",
                "raw_data": {
                    "keyword": keyword,
                    "page": pg,
                    "company_url": company_url,
                    "job_url": normalized_jd_url,
                    "card_text": card_text[:1200],
                    "card_parsed": parsed,
                    "search_url": page.url,
                    "zhaopin_click": {
                        "card_index": len(results),
                        "jd_url_raw": jd_url,
                        "jd_title": jd_title,
                        "company_name": company,
                    },
                },
            })
        except Exception as exc:
            if inspect:
                print(f"[INSPECT] 卡片解析异常: {exc}")
            continue
    print(f"[INFO] zhaopin 卡片过滤后保留 {len(results)} 条")
    return results


# 连续被安全验证挡住时累计；超过阈值后整批 enrich 短路，避免每条都等 60s
_zhaopin_verify_streak = 0
_ZHAOPIN_VERIFY_GIVEUP = 3


def _zhaopin_detail_id(url: str) -> str:
    m = re.search(r"(?:jobdetail/|jobs?\.zhaopin\.com/)([^/?#]+)", url or "", re.I)
    return re.sub(r"\.html?$", "", m.group(1)) if m else ""


async def _prepare_zhaopin_click(list_page, entry: dict) -> dict:
    raw = entry.get("raw_data") or {}
    click_hint = raw.get("zhaopin_click") if isinstance(raw, dict) else {}
    target_url = entry.get("source_url", "")
    payload = {
        "targetUrl": target_url,
        "targetId": _zhaopin_detail_id(target_url),
        "title": entry.get("jd_title", ""),
        "company": entry.get("company_name", ""),
        "cardIndex": (click_hint or {}).get("card_index"),
    }
    return await list_page.evaluate(
        """(payload) => {
          const selector = [
            "a[href*='jobs.zhaopin.com']",
            "a[href*='zhaopin.com/jobdetail']",
            "a[href*='zhaopin.com/job/']",
            "a[href*='zhaopin.com/position']",
            "a[href*='zhaopin.com/product/position']"
          ].join(',');
          const clean = (v) => String(v || '').replace(/\\s+/g, ' ').trim();
          const abs = (href) => {
            try { return new URL(href || '', location.href).href; } catch { return href || ''; }
          };
          const norm = (url) => {
            try {
              const u = new URL(url, location.href);
              u.hash = '';
              return u.href.replace(/\\/$/, '');
            } catch {
              return String(url || '').replace(/\\/$/, '');
            }
          };
          const anchors = Array.from(document.querySelectorAll(selector))
            .filter(a => abs(a.getAttribute('href') || a.href));
          const targetUrl = norm(payload.targetUrl);
          const targetId = clean(payload.targetId);
          const title = clean(payload.title).toLowerCase();
          const company = clean(payload.company).toLowerCase();
          const rows = anchors.map((a, index) => {
            const card = a.closest("li, div[class*='job'], div[class*='position'], div[class*='item'], div[class*='content']") || a.parentElement;
            const text = clean((card && card.innerText) || a.innerText || '');
            const href = norm(abs(a.getAttribute('href') || a.href));
            return { index, href, text, linkText: clean(a.innerText || '') };
          });
          let row = rows.find(r => targetUrl && r.href === targetUrl)
            || rows.find(r => targetId && r.href.includes(targetId))
            || rows.find(r => title && r.text.toLowerCase().includes(title) && (!company || r.text.toLowerCase().includes(company)))
            || (Number.isInteger(payload.cardIndex) ? rows[payload.cardIndex] : null);
          if (!row) {
            return { ok: false, reason: 'anchor_not_found', anchor_count: rows.length, sample: rows.slice(0, 5) };
          }
          const anchor = anchors[row.index];
          anchor.scrollIntoView({ block: 'center', inline: 'center' });
          anchor.setAttribute('target', '_blank');
          anchor.setAttribute('rel', 'noopener');
          const rect = anchor.getBoundingClientRect();
          if (!rect.width || !rect.height) {
            return { ok: false, reason: 'anchor_not_visible', href: row.href, text: row.linkText || row.text };
          }
          return {
            ok: true,
            x: Math.round(rect.left + rect.width / 2),
            y: Math.round(rect.top + rect.height / 2),
            href: row.href,
            text: row.linkText || row.text,
            index: row.index,
          };
        }""",
        payload,
    )


async def _zhaopin_debugger_click(list_page, click_target: dict) -> dict:
    request_id = f"zp-click-{int(time.time() * 1000)}-{random.randint(1000, 9999)}"
    return await list_page.evaluate(
        """({ requestId, x, y }) => new Promise((resolve) => {
          const requestSource = 'companyleads:zhaopin-click-request';
          const responseSource = 'companyleads:zhaopin-click-response';
          const timeout = setTimeout(() => {
            window.removeEventListener('message', onMessage);
            resolve({ ok: false, reason: 'extension_bridge_timeout' });
          }, 8000);
          function onMessage(event) {
            if (event.source !== window) return;
            const data = event.data || {};
            if (data.source !== responseSource || data.requestId !== requestId) return;
            clearTimeout(timeout);
            window.removeEventListener('message', onMessage);
            resolve(data.response || { ok: false, reason: 'empty_bridge_response' });
          }
          window.addEventListener('message', onMessage);
          window.postMessage({ source: requestSource, requestId, x, y }, '*');
        })""",
        {
            "requestId": request_id,
            "x": click_target.get("x"),
            "y": click_target.get("y"),
        },
    )


async def _open_zhaopin_detail_by_click(list_page, entry: dict, timeout_ms: int = 15_000):
    raw = entry.setdefault("raw_data", {})
    if not isinstance(raw, dict):
        raw = {"raw": raw}
        entry["raw_data"] = raw
    try:
        await list_page.bring_to_front()
        click_target = await _prepare_zhaopin_click(list_page, entry)
    except Exception as exc:
        raw["zhaopin_click_skipped_reason"] = f"prepare_failed:{exc}"
        return None, "prepare_failed"

    if not click_target.get("ok"):
        raw["zhaopin_click_skipped_reason"] = click_target.get("reason") or "anchor_not_found"
        raw["zhaopin_click_debug"] = click_target
        print(f"[ZHAOPIN-CLICK] skip {entry.get('company_name', '?')[:30]} / {entry.get('jd_title', '?')[:30]}: {raw['zhaopin_click_skipped_reason']}")
        return None, raw["zhaopin_click_skipped_reason"]

    detail_page = None
    try:
        existing_pages = set(list_page.context.pages)
        await rnd_delay(0.4, 1.2)
        click_result = await _zhaopin_debugger_click(list_page, click_target)
        if not click_result.get("ok"):
            raw["zhaopin_click_skipped_reason"] = click_result.get("reason") or "debugger_click_failed"
            raw["zhaopin_click_debug"] = click_result
            return None, raw["zhaopin_click_skipped_reason"]
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            new_pages = [p for p in list_page.context.pages if p not in existing_pages and not p.is_closed()]
            if new_pages:
                detail_page = new_pages[-1]
                break
            await asyncio.sleep(0.2)
        if not detail_page:
            raise PlaywrightTimeoutError("no new zhaopin detail tab opened")
    except PlaywrightTimeoutError:
        raw["zhaopin_click_skipped_reason"] = "new_tab_timeout"
        raw["zhaopin_click_debug"] = click_target
        return None, "new_tab_timeout"

    try:
        await detail_page.wait_for_load_state("domcontentloaded", timeout=25_000)
    except Exception:
        pass
    raw["zhaopin_click_opened_url"] = detail_page.url
    return detail_page, ""


async def enrich_zhaopin(page, entry: dict, captcha_timeout: int = 60) -> dict:
    """从智联列表页点击打开职位详情，补齐与 qzrc 公司线索一致的字段面。
    遇到 EdgeOne / Cloudflare 安全验证页时短路并打 [VERIFY]，绝不覆盖原字段。"""
    global _zhaopin_verify_streak
    if _zhaopin_verify_streak >= _ZHAOPIN_VERIFY_GIVEUP:
        # 已连续多次被拦，本批后续条全部跳过 enrich
        return entry
    url = entry.get("source_url", "")
    if not url or not url.startswith("http"):
        return entry
    if not re.search(r"(jobs?\.zhaopin\.com|/jobs?/|jobdetail)", url, re.I):
        return entry
    detail_page = None
    close_detail_page = True
    try:
        detail_page, open_reason = await _open_zhaopin_detail_by_click(page, entry)
        if not detail_page:
            return entry
        detail = detail_page
        await rnd_delay(1.5, 3)

        # ─── 安全验证页识别（EdgeOne / Cloudflare）──
        sec_hit, sec_token = await check_security_page(detail)
        if sec_hit:
            raw = entry.setdefault("raw_data", {})
            if not isinstance(raw, dict):
                raw = {"raw": raw}
                entry["raw_data"] = raw
            raw["zhaopin_security_hold"] = True
            raw["zhaopin_security_token"] = sec_token
            raw["zhaopin_security_url"] = detail.url
            await detail.bring_to_front()
            print(f"[VERIFY] 智联详情页被安全验证拦截 ({sec_token}): {detail.url[:80]}")
            print(f"        请在打开的浏览器窗口手动勾选/点击通过验证（最多等 {captcha_timeout}s）")
            # 等用户手动通过；超时则跳过这条
            if not await wait_captcha(detail, captcha_timeout):
                _zhaopin_verify_streak += 1
                close_detail_page = False
                print(f"[VERIFY] 验证未通过 (连续第 {_zhaopin_verify_streak} 次)，保留原字段不覆盖")
                if _zhaopin_verify_streak >= _ZHAOPIN_VERIFY_GIVEUP:
                    print(f"[VERIFY] 连续 {_zhaopin_verify_streak} 次被拦截 → 本批后续 enrich 全部跳过；"
                          f"请改用交互模式手动通过验证，或换个时间/IP 再试")
                return entry
            # 验证通过后再确认一次没有残留拦截
            still, _ = await check_security_page(detail)
            if still:
                _zhaopin_verify_streak += 1
                raw["zhaopin_security_hold"] = True
                close_detail_page = False
                return entry
            raw["zhaopin_security_hold"] = False
            _zhaopin_verify_streak = 0   # 通过 → 计数清零

        if await check_captcha(detail):
            await detail.bring_to_front()
            if not await wait_captcha(detail, captcha_timeout):
                raw = entry.setdefault("raw_data", {})
                if isinstance(raw, dict):
                    raw["zhaopin_security_hold"] = True
                close_detail_page = False
                return entry

        # 走到这说明页面不是验证页 → 重置连续验证计数
        _zhaopin_verify_streak = 0

        body_text = clean(await detail.evaluate("() => document.body ? document.body.innerText : ''"))
        # 防御：body_text 仍像验证页（极短 / 含验证关键字）→ 跳过
        if len(body_text) < 100 or any(tok in body_text[:300] for tok in _SECURITY_PAGE_TOKENS):
            print(f"[VERIFY] 详情页内容异常（疑似验证页未跳过），保留原字段: {entry.get('company_name', '?')[:30]}")
            return entry

        title = await first_text(detail, [
            "h1", ".job-title", "[class*='job-title']", "[class*='position-title']",
        ])
        company = await first_text(detail, [
            "a.company-name", ".company-name", "[class*='company-name']",
            "[class*='companyName']", "[class*='company'] a",
        ])
        if len(company) > 80:
            m = re.search(r"(?:公司名称|招聘单位|企业名称)[\s:：]+([^|\n]{2,80})", body_text)
            company = clean(m.group(1)) if m else ""
        # 防御：title/company 看起来像域名/噪声 → 不要覆盖原字段
        if title and not _looks_like_domain_or_noise(title):
            entry["jd_title"] = title[:300]
        if company and not _looks_like_domain_or_noise(company) and not is_excluded_company(company):
            entry["company_name"] = company[:300]

        salary = await first_text(detail, [".salary", "[class*='salary']", "[class*='job-salary']"])
        if salary:
            entry["salary_range"] = salary[:120]

        jd_desc = ""
        for sel in [
            ".job-detail", ".describtion", ".description", ".job-desc",
            "[class*='job-detail']", "[class*='jobDescription']",
            "[class*='description']",
        ]:
            el = await detail.query_selector(sel)
            if not el:
                continue
            txt = clean(await el.inner_text())
            if len(txt) > 20 and any(k in txt for k in ("职位", "岗位", "职责", "要求", "任职")):
                jd_desc = txt
                break
        if not jd_desc:
            m = re.search(
                r"(?:职位描述|岗位职责|任职要求|工作职责)[\s:：]+(.{30,2200}?)(?=公司介绍|公司简介|工作地址|职位福利|$)",
                body_text,
            )
            if m:
                jd_desc = m.group(1)
        if jd_desc:
            entry["jd_description"] = jd_desc[:2000]
            entry.update(extract_contacts(jd_desc))

        desc = ""
        for sel in [
            ".company-intro", ".company-about", ".company-info", ".company-profile",
            "[class*='company-intro']", "[class*='companyInfo']",
            "[class*='company-profile']", "[class*='company'] [class*='intro']",
        ]:
            el = await detail.query_selector(sel)
            if not el:
                continue
            txt = clean(await el.inner_text())
            if len(txt) > 20:
                desc = txt
                break
        if not desc:
            m = re.search(
                r"(?:公司介绍|公司简介|企业介绍|企业简介)[\s:：]+(.{30,2200}?)(?=工商信息|工作地址|公司地址|在招职位|$)",
                body_text,
            )
            if m:
                desc = m.group(1)
        if desc:
            entry["company_description"] = desc[:2000]

        addr = await first_text(detail, [
            ".job-address", ".company-address", "[class*='address']",
            "[class*='work-address']", "[class*='jobAddress']",
        ])
        if not addr:
            m = re.search(r"(?:工作地址|公司地址|上班地址)[\s:：]+([^|\n]{4,180})", body_text)
            if m:
                addr = m.group(1)
        if addr:
            entry["company_address"] = addr[:300]

        for label, key in [
            ("行业", "industry"),
            ("公司规模", "size_range"),
            ("规模", "size_range"),
            ("城市", "city"),
        ]:
            if entry.get(key):
                continue
            m = re.search(rf"{label}[\s:：]+([^|\n]{{2,80}})", body_text)
            if m:
                entry[key] = clean(m.group(1))[:120]

        cid = extract_zhaopin_company_id(detail.url, body_text)
        if cid:
            entry["platform_company_id"] = entry.get("platform_company_id") or cid
        raw = entry.get("raw_data") or {}
        raw.update({"detail_text": body_text[:2500]})
        entry["raw_data"] = raw
    except Exception as exc:
        print(f"[ENRICH] 智联详情页补全失败: {exc}")
    finally:
        if detail_page and not detail_page.is_closed() and close_detail_page:
            try:
                await detail_page.close()
            except Exception:
                pass
        if not page.is_closed():
            try:
                await page.bring_to_front()
            except Exception:
                pass
    return entry


# ---------------------------------------------------------------------------
# Zhaopin · 简历搜索（招聘端，需企业会员登录）
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 51job · 企业端人才搜索（招聘端，需企业会员登录）
# ---------------------------------------------------------------------------

_JOB51_TALENT_SOURCE_TYPE = "enterprise_resume_search"
_JOB51_TALENT_CONSENT = "account_visible"
_JOB51_TALENT_PERMISSION = "登录企业端可见简历搜索数据；隐藏联系方式、验证码绕过、自动简历下载不在首版范围。"

_JOB51_TALENT_MENU = [
    "#sensor_talentsearch_menu",
    "li:has-text('人才搜索')",
    ".eh_menu_item:has-text('人才搜索')",
    "text=人才搜索",
]
_JOB51_TALENT_INPUT = [
    "input[placeholder='跨境电商']",
    "input[placeholder*='搜索']",
    "input[placeholder*='关键字']",
    "input[placeholder*='关键词']",
    "input[placeholder*='职位']",
    "input[placeholder*='简历']",
    "input[type='search']",
    ".search-input input",
    ".keyword input",
]
_JOB51_TALENT_LIST = [
    ".resume-list",
    ".talent-list",
    ".candidate-list",
    ".list",
    "table",
    "[class*='resume']",
    "[class*='candidate']",
]
_JOB51_TALENT_ITEMS = [
    ".resume-card",
    ".resume-list .resume-item",
    ".resume-item",
    ".talent-item",
    ".candidate-item",
    "tr:has(a)",
    "[class*='resume'][class*='item']",
    "[class*='candidate'][class*='item']",
]
_JOB51_TALENT_LOADING = ["text=Loading...", "text=加载中", ".el-loading-mask", ".loading", ".van-loading"]
_JOB51_TALENT_EMPTY = [
    "text=暂无相关简历",
    "text=暂无人才",
    "text=没有找到",
    "text=未找到",
    "text=暂无数据",
    "text=无搜索结果",
    ".empty",
    ".no-data",
    ".no-result",
]
_JOB51_TALENT_LOGIN = ["text=登录", "text=请先登录", "input[type='password']", "input[placeholder*='密码']"]
_JOB51_TALENT_DETAIL = [
    "a[href*='resume']",
    "a[href*='Resume']",
    "a[href*='candidate']",
    "a[href*='Candidate']",
    "a[href*='talent']",
    "a[href*='detail']",
    "a",
]

_JOB51_FIELD_ALIASES = {
    "id": ("resumeId", "resume_id", "candidateId", "candidate_id", "userId", "userid", "real_userid", "user_id", "id", "guid", "rid"),
    "name": ("resume_name", "name", "userName", "username", "realName", "realname", "resumeName", "姓名", "名称"),
    "desired_title": (
        "desiredTitle", "expectPosition", "expect_position", "expectJob", "jobIntention", "intentionJob",
        "currentTitle", "position", "jobName", "job_intention", "expectJobName", "expect_job_name",
        "title", "求职意向", "意向职位", "期望职位", "当前岗位",
    ),
    "city": ("city", "expectCity", "expect_city", "workCity", "area", "location", "base_info", "意向城市", "意向地区", "城市", "地区"),
    "experience": ("experience", "workYear", "work_year", "workYears", "years", "工作经验", "经验"),
    "education": ("education", "educationName", "degree", "学历"),
    "major": ("major", "speciality", "profession", "专业"),
    "salary": ("salary", "salaryExpectation", "expectSalary", "salaryRange", "期望薪资", "薪资"),
    "summary": (
        "summary", "selfEvaluation", "self_evaluation", "description", "intro", "workExperience",
        "resumeSummary", "recent_work_info", "label_list", "work_list", "education_list",
        "sorted_skill_tag_list", "classify_skill_tags_list", "自我评价", "简历摘要", "工作经历",
    ),
    "url": ("sourceUrl", "source_url", "resumeUrl", "resume_url", "detailUrl", "detail_url", "url", "href", "link"),
}


def _norm_key(value: str) -> str:
    return re.sub(r"[_\-\s]", "", value or "").lower()


def _norm_value(value) -> str:
    if isinstance(value, list):
        return clean(" ".join(_norm_value(v) for v in value if v is not None))
    if isinstance(value, dict):
        return clean(" ".join(_norm_value(v) for v in value.values() if v is not None))
    return clean(re.sub(r"</?em>", "", str(value or "")))


def _job51_obj(record: dict, key: str) -> dict:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _job51_arr(record: dict, key: str) -> list[dict]:
    value = record.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _job51_text(record: dict, key: str) -> str:
    return _norm_value(record.get(key))


def _job51_alias(record: dict, aliases: tuple[str, ...], depth: int = 0) -> str:
    alias_set = {_norm_key(a) for a in aliases}
    for key, value in record.items():
        if _norm_key(str(key)) in alias_set:
            text = _norm_value(value)
            if text:
                return text
    if depth >= 4:
        return ""
    for value in record.values():
        if isinstance(value, dict):
            nested = _job51_alias(value, aliases, depth + 1)
            if nested:
                return nested
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    nested = _job51_alias(item, aliases, depth + 1)
                    if nested:
                        return nested
    return ""


def is_51job_search_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return "we.51job.com" in parsed.netloc.lower() and "/pc/search" in parsed.path.lower()


def prefer_detail_url(*urls: str) -> str:
    for url in urls:
        if url and url.startswith("http") and not is_51job_search_url(url):
            return url
    return next((url for url in urls if url), "")


def _job51_record_score(record: dict) -> int:
    keys = {_norm_key(str(k)) for k in record.keys()}

    def has_any(name: str) -> bool:
        return any(_norm_key(alias) in keys for alias in _JOB51_FIELD_ALIASES[name])

    return (
        (2 if has_any("id") else 0)
        + (2 if has_any("name") else 0)
        + (3 if has_any("desired_title") else 0)
        + (1 if has_any("city") else 0)
        + (1 if has_any("experience") else 0)
        + (1 if has_any("education") else 0)
    )


def _job51_talent_arrays(value, depth: int = 0) -> list[list[dict]]:
    if depth > 8 or value is None:
        return []
    if isinstance(value, list):
        objects = [item for item in value if isinstance(item, dict)]
        nested: list[list[dict]] = []
        for item in value[:80]:
            nested.extend(_job51_talent_arrays(item, depth + 1))
        direct_score = sum(_job51_record_score(item) for item in objects[:20])
        if objects and direct_score >= max(4, min(len(objects), 20) * 2):
            return [objects, *nested]
        return nested
    if isinstance(value, dict):
        out: list[list[dict]] = []
        for item in value.values():
            out.extend(_job51_talent_arrays(item, depth + 1))
        return out
    return []


def _job51_resolve_url(raw_url: str, base_url: str) -> str:
    if not raw_url:
        return base_url
    try:
        return urljoin(base_url, raw_url)
    except Exception:
        return base_url


def _job51_resume_id(source_url: str, fallback: str = "") -> str:
    for pattern in (
        r"[?&](?:resumeId|resume_id|candidateId|candidate_id|userId|rid)=([^&#]+)",
        r"/(?:resume|Resume|candidate|Candidate|talent|detail)[/-]([^/?#]+)",
        r"/([^/?#]*(?:resume|candidate)[^/?#]*)",
    ):
        m = re.search(pattern, source_url or "", re.I)
        if m:
            return m.group(1)
    return fallback


def _job51_talent_entry(candidate: dict, raw_data: dict, keyword: str) -> dict:
    source_url = candidate.get("source_url") or ""
    rid = candidate.get("platform_resume_id") or _job51_resume_id(source_url)
    return {
        "platform": "51job_talent",
        "platform_resume_id": rid,
        "name_masked": candidate.get("name_masked", ""),
        "desired_title": candidate.get("desired_title", ""),
        "city": candidate.get("city", ""),
        "experience": candidate.get("experience", ""),
        "education": candidate.get("education", ""),
        "major": candidate.get("major", ""),
        "salary_expectation": candidate.get("salary_expectation", ""),
        "source_url": source_url,
        "resume_download_url": "",
        "raw_summary": candidate.get("raw_summary", ""),
        "raw_data": raw_data,
        "source_type": _JOB51_TALENT_SOURCE_TYPE,
        "consent_status": _JOB51_TALENT_CONSENT,
        "permission_note": _JOB51_TALENT_PERMISSION,
        "status": "new",
        "notes": f"keyword={keyword}" if keyword else "",
    }


def _parse_51job_talent_record(record: dict, keyword: str, base_url: str) -> dict | None:
    platform_resume_id = _job51_text(record, "userid") or _job51_text(record, "real_userid")
    base_info = _job51_obj(record, "base_info")
    job_intention = _job51_obj(record, "job_intention")
    recent_work = _job51_obj(record, "recent_work_info")
    if not platform_resume_id or not base_info:
        return None

    first_edu = (_job51_arr(record, "education_list") or [{}])[0]
    work_summary = " | ".join(
        clean(" ".join(
            _job51_text(item, key)
            for key in ("company_name", "job_name", "work_func_value", "working_years")
            if _job51_text(item, key)
        ))
        for item in _job51_arr(record, "work_list")
    )
    labels = _norm_value([
        record.get("label_list"),
        record.get("label_sorted_skill_tag_list"),
        record.get("classify_skill_tags_list"),
        record.get("sorted_skill_tag_list"),
    ])
    raw_summary = _norm_value([
        _job51_text(recent_work, "recent_company"),
        _job51_text(recent_work, "recent_position"),
        work_summary,
        labels,
        _job51_text(record, "highlight"),
        _job51_text(record, "resume_slicing"),
    ])
    return _job51_talent_entry({
        "platform_resume_id": platform_resume_id,
        "name_masked": _job51_text(base_info, "resume_name") or _job51_text(record, "name"),
        "desired_title": _job51_text(job_intention, "expect_work_function_value") or _job51_text(recent_work, "recent_position"),
        "city": _job51_text(job_intention, "expect_job_area_value") or _job51_text(base_info, "usual_area_value") or _job51_text(base_info, "area_value"),
        "experience": _job51_text(base_info, "work_year_value"),
        "education": _job51_text(base_info, "top_degree_value") or _job51_text(first_edu, "degree_value"),
        "major": _job51_text(base_info, "top_major_value") or _job51_text(first_edu, "major_value"),
        "salary_expectation": _job51_text(job_intention, "new_expect_salary") or _job51_text(job_intention, "expect_salary"),
        "source_url": base_url,
        "raw_summary": raw_summary,
    }, record, keyword)


def parse_51job_talent_json(payloads: list[dict], keyword: str, base_url: str) -> list[dict]:
    results: list[dict] = []
    for payload in payloads:
        for items in _job51_talent_arrays(payload):
            for record in items:
                parsed = _parse_51job_talent_record(record, keyword, base_url)
                if not parsed:
                    raw_url = _job51_alias(record, _JOB51_FIELD_ALIASES["url"])
                    source_url = _job51_resolve_url(raw_url, base_url)
                    parsed = _job51_talent_entry({
                        "platform_resume_id": _job51_alias(record, _JOB51_FIELD_ALIASES["id"]) or _job51_resume_id(source_url),
                        "name_masked": _job51_alias(record, _JOB51_FIELD_ALIASES["name"]),
                        "desired_title": _job51_alias(record, _JOB51_FIELD_ALIASES["desired_title"]),
                        "city": _job51_alias(record, _JOB51_FIELD_ALIASES["city"]),
                        "experience": _job51_alias(record, _JOB51_FIELD_ALIASES["experience"]),
                        "education": _job51_alias(record, _JOB51_FIELD_ALIASES["education"]),
                        "major": _job51_alias(record, _JOB51_FIELD_ALIASES["major"]),
                        "salary_expectation": _job51_alias(record, _JOB51_FIELD_ALIASES["salary"]),
                        "source_url": source_url,
                        "raw_summary": _job51_alias(record, _JOB51_FIELD_ALIASES["summary"]),
                    }, record, keyword)
                text = " ".join([
                    parsed.get("desired_title") or "",
                    parsed.get("city") or "",
                    parsed.get("experience") or "",
                    parsed.get("education") or "",
                    parsed.get("major") or "",
                    parsed.get("salary_expectation") or "",
                    parsed.get("raw_summary") or "",
                    json.dumps(record, ensure_ascii=False, default=str),
                ])
                if (parsed.get("platform_resume_id") or parsed.get("name_masked") or parsed.get("desired_title")) and has_crossborder([keyword, text]):
                    results.append(parsed)
    return _dedupe_talent_entries(results)


def parse_51job_talent_dom_text(text: str, keyword: str, source_url: str) -> dict | None:
    normalized = clean(text)
    if not normalized or not has_crossborder([keyword, normalized]):
        return None
    name = re.search(r"(?:姓名|候选人)[:：]?\s*([\u4e00-\u9fa5A-Za-z*]{1,12})", normalized)
    title = re.search(r"(?:求职意向|意向职位|期望职位|当前岗位)[:：]?\s*([^|，,。]{2,40}?)(?=\s*(?:城市|现居住地|工作经验|经验|学历|期望薪资|薪资|$))", normalized)
    education = re.search(r"(博士|硕士|研究生|本科|大专|中专|高中)", normalized)
    experience = re.search(r"(?:\d+\s*-\s*\d+年|\d+年以上|\d+年经验|应届|无经验)", normalized)
    salary = re.search(r"(?:\d+\s*-\s*\d+\s*[Kk千万]?|面议|[\u4e00-\u9fa5]*薪资[:：]?\s*[^|，,。]{2,20})", normalized)
    city = re.search(r"(?:泉州|厦门|福州|深圳|广州|杭州|上海|北京|义乌|东莞|晋江|石狮|南安|丰泽|鲤城|洛江|惠安|南宁)", normalized)
    return _job51_talent_entry({
        "platform_resume_id": _job51_resume_id(source_url),
        "name_masked": name.group(1) if name else "",
        "desired_title": title.group(1) if title else "",
        "city": city.group(0) if city else "",
        "experience": experience.group(0) if experience else "",
        "education": education.group(0) if education else "",
        "major": "",
        "salary_expectation": salary.group(0) if salary else "",
        "source_url": source_url,
        "raw_summary": normalized[:1000],
    }, {"source": "dom", "text": normalized[:1500]}, keyword)


def _dedupe_talent_entries(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for entry in entries:
        key = entry.get("platform_resume_id") or f"{entry.get('name_masked')}:{entry.get('desired_title')}:{entry.get('source_url')}"
        key = f"{entry.get('platform')}:{key}"
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _entry_key(entry: dict) -> str:
    """生成单条线索的去重键，公司/人才两类通用。

    优先用平台主键（公司 ID / 简历 ID），其次用详情 URL，
    最后退化到 公司名+职位 / 姓名+期望职位 组合，避免翻页拿到重复数据时反复入库。
    """
    if not isinstance(entry, dict):
        return repr(entry)
    platform = entry.get("platform") or ""
    pid = (
        entry.get("platform_company_id")
        or entry.get("platform_resume_id")
        or ""
    )
    if pid:
        return f"{platform}:id:{pid}"
    url = entry.get("source_url") or ""
    if url:
        return f"{platform}:url:{url}"
    name = entry.get("company_name") or entry.get("name_masked") or ""
    title = entry.get("jd_title") or entry.get("desired_title") or ""
    return f"{platform}:nt:{name}:{title}"


async def _visible_locator(page, selectors: list[str]):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=800):
                return loc
        except Exception:
            continue
    return None


async def _has_visible(page, selectors: list[str]) -> bool:
    return await _visible_locator(page, selectors) is not None


async def _is_51job_talent_login(page) -> bool:
    if "ehire.51job.com/Revision/login" in page.url:
        return True
    return await _has_visible(page, _JOB51_TALENT_LOGIN)


async def _is_51job_talent_search(page) -> bool:
    if re.search(r"ehire\.51job\.com/Revision/talent/search", page.url, re.I):
        return True
    try:
        title = await page.title()
    except Exception:
        title = ""
    if "人才搜索" in title:
        return True
    try:
        body = await page.locator("body").inner_text(timeout=1000)
    except Exception:
        body = ""
    return "人才搜索" in body and "输入关键词搜索" in body


async def wait_51job_talent_login_if_needed(page, timeout: int) -> bool:
    if not await _is_51job_talent_login(page):
        return True
    timeout = max(timeout, 600)
    print("[LOGIN] 前程无忧企业端当前处于登录页，请先在受控 Chrome 中完成登录；脚本会停在当前页等待，不会自动跳到人才搜索。")
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.is_closed():
            print("[LOGIN] 前程无忧企业端页面已关闭，停止当前采集。")
            return False
        if not await _is_51job_talent_login(page):
            print("[LOGIN] 前程无忧企业端登录态检查通过，继续采集。")
            return True
        await asyncio.sleep(2)
    print(f"[LOGIN] 前程无忧企业端登录等待超时 ({timeout}s)，停止当前采集。")
    return False


async def open_51job_talent_search(page, captcha_timeout: int) -> bool:
    if not await wait_51job_talent_login_if_needed(page, captcha_timeout):
        return False
    url = JOB51_TALENT_SEARCH.format(ts=int(time.time() * 1000))
    try:
        await page.goto(url, timeout=30_000, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    await rnd_delay(1, 1.5)
    if await _is_51job_talent_login(page):
        if not await wait_51job_talent_login_if_needed(page, captcha_timeout):
            return False
    if await _is_51job_talent_search(page):
        return True
    menu = await _visible_locator(page, _JOB51_TALENT_MENU)
    if menu:
        try:
            await menu.click(timeout=5000)
            await page.wait_for_load_state("domcontentloaded", timeout=15_000)
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await rnd_delay(1, 1.5)
    if await _is_51job_talent_login(page):
        if not await wait_51job_talent_login_if_needed(page, captcha_timeout):
            return False
    if not await _is_51job_talent_search(page):
        print(f"[ERROR] Unable to enter 51job talent search page: {page.url}")
        return False
    return True


async def _find_51job_talent_input(page):
    primary = page.locator("input[placeholder='跨境电商']").first
    try:
        if await primary.is_visible(timeout=2000):
            return primary
    except Exception:
        pass

    excluded = re.compile(r"期望工作地|性别|求职状态|请输入姓名|输入岗位名称|请输入")
    candidates = page.locator("input.el-input__inner,input[type='search'],input[type='text']")
    count = await candidates.count()
    for index in range(count):
        item = candidates.nth(index)
        try:
            visible = await item.is_visible(timeout=500)
            disabled = await item.get_attribute("disabled")
            placeholder = await item.get_attribute("placeholder") or ""
        except Exception:
            continue
        if visible and disabled is None and not excluded.search(placeholder):
            return item
    return await _visible_locator(page, _JOB51_TALENT_INPUT)


async def _click_51job_talent_search(page) -> None:
    buttons = page.locator("button:has-text('搜索')")
    try:
        count = await buttons.count()
    except Exception:
        count = 0
    for index in range(count):
        button = buttons.nth(index)
        try:
            if await button.is_visible(timeout=500):
                await button.click(timeout=5000)
                return
        except Exception:
            continue
    button = await _visible_locator(page, [
        "button:has-text('搜索')",
        "button:has-text('搜简历')",
        "button:has-text('找人才')",
        ".search-btn",
        ".btn-search",
        "button[type='submit']",
    ])
    if button:
        await button.click(timeout=5000)
    else:
        await page.keyboard.press("Enter")


async def search_51job_talent_keyword(page, keyword: str) -> bool:
    input_box = await _find_51job_talent_input(page)
    if not input_box:
        print("[ERROR] 前程无忧人才搜索输入框未找到")
        return False
    await input_box.fill(keyword)
    await _click_51job_talent_search(page)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    await rnd_delay(1.5, 2.5)
    return True


async def wait_51job_talent_results(page, keyword: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        list_visible = await _has_visible(page, _JOB51_TALENT_LIST)
        empty_visible = await _has_visible(page, _JOB51_TALENT_EMPTY)
        loading_visible = await _has_visible(page, _JOB51_TALENT_LOADING)
        if (list_visible or empty_visible) and not loading_visible:
            return
        print(f"[WAIT] 前程无忧人才搜索结果加载中 keyword={keyword!r} url={page.url}")
        await asyncio.sleep(1)


async def parse_51job_talent_dom(page, keyword: str) -> list[dict]:
    entries: list[dict] = []
    items = page.locator(",".join(_JOB51_TALENT_ITEMS))
    try:
        count = await items.count()
    except Exception:
        count = 0
    for index in range(min(count, 80)):
        item = items.nth(index)
        try:
            text = await item.inner_text(timeout=2000)
        except Exception:
            continue
        href = ""
        for sel in _JOB51_TALENT_DETAIL:
            try:
                link = item.locator(sel).first
                href = await link.get_attribute("href", timeout=1000) or ""
                if href:
                    break
            except Exception:
                continue
        source_url = urljoin(page.url, href) if href else page.url
        entry = parse_51job_talent_dom_text(text, keyword, source_url)
        if entry:
            entries.append(entry)
    if entries:
        return _dedupe_talent_entries(entries)
    try:
        body = await page.locator("body").inner_text(timeout=2000)
    except Exception:
        body = ""
    entry = parse_51job_talent_dom_text(body, keyword, page.url)
    return [entry] if entry else []


async def scrape_51job_talent_page(page, capture_data: list[dict], keyword: str, pg: int,
                                   captcha_timeout: int, inspect: bool = False) -> list[dict]:
    if pg <= 1:
        if not await open_51job_talent_search(page, captcha_timeout):
            return []
        capture_data.clear()
        if not await search_51job_talent_keyword(page, keyword):
            return []
    else:
        # 前程无忧人才为下拉懒加载：向下滚动刷新出更多简历，而不是点击翻页按钮。
        # 滚动后重新解析当前全部已加载结果，由上层驱动循环按 _entry_key 去重；
        # 若未加载出新数据，会被“翻页未推进/全部重复”逻辑判定并停止当前关键词。
        capture_data.clear()
        await _scroll_to_load_more(page, rounds=8)
        await rnd_delay(1, 2)

    if await check_captcha(page):
        if not await wait_captcha(page, captcha_timeout):
            return []
    sec_hit, sec_token = await check_security_page(page)
    if sec_hit:
        print(f"[CAPTCHA] 前程无忧人才搜索命中安全验证页 ({sec_token})，停批")
        return []

    await wait_51job_talent_results(page, keyword)
    await rnd_delay(1, 2)
    fallback_url = page.url
    preferred = [cap.get("body") for cap in capture_data if re.search(r"/resume/search/talent_hunt_resume_list", cap.get("url", ""), re.I)]
    payloads = preferred or [cap.get("body") for cap in capture_data]

    if inspect:
        print(f"\n[INSPECT-API] 前程无忧人才拦截到 {len(capture_data)} 个 JSON 响应:")
        for cap in capture_data[-12:]:
            body = cap.get("body")
            shape = list(body.keys())[:12] if isinstance(body, dict) else f"array[{len(body)}]" if isinstance(body, list) else type(body).__name__
            print(f"  URL : {cap.get('url')}")
            print(f"  形状: {shape}")

    results = parse_51job_talent_json([p for p in payloads if isinstance(p, (dict, list))], keyword, fallback_url)
    if results:
        print(f"Parsed talent rows from JSON responses: keyword={keyword!r} count={len(results)}")
        return results
    results = await parse_51job_talent_dom(page, keyword)
    print(f"[INFO] Parsed talent rows from DOM fallback: keyword={keyword!r} count={len(results)}")
    return results

# 候选简历字段名（按常见 zhaopin RP 接口归纳）
_ZP_TALENT_SOURCE_TYPE = "enterprise_resume_search"
_ZP_TALENT_CONSENT = "account_visible"
_ZP_TALENT_PERMISSION = "登录智联企业端可见搜索人才数据；隐藏联系方式、验证码绕过、自动简历下载不在首版范围。"
_ZP_TALENT_INPUT = [
    "input.keyword-input-tag-item-input__input",
    ".keyword-input-tag-item-input__input",
    "xpath=/html/body/div[1]/div[2]/div[1]/div/div[1]/div[1]//input",
    "xpath=/html/body/div[1]/div[2]/div[1]/div/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div/div/div[2]/div/div[2]/div[1]//input",
    "input[placeholder*='搜索人才']",
    "input[placeholder*='搜索简历']",
    "input[placeholder*='请输入关键词']",
    "input[placeholder*='关键词']",
    "input[placeholder*='职位']",
    "input[placeholder*='人才']",
    "input[placeholder*='简历']",
    ".k-input input",
    "input[type='search']",
    "input[type='text']",
]
_ZP_TALENT_CLICK_TARGETS = [
    "xpath=/html/body/div[1]/div[2]/div[1]/div/div[1]/div[1]/div[2]/div[2]/div[1]/div[1]/div/div/div[2]/div/div[2]/div[1]",
    "xpath=/html/body/div[1]/div[2]/div[1]/div/div[1]/div[1]",
    ".keyword-input-tag-item-input",
    ".keyword-input-tag-item-input__input",
    "[class*='keyword-input']",
    "[class*='search-input']",
]
_ZP_TALENT_LIST = [
    ".resume-list",
    ".candidate-list",
    ".talent-list",
    "[class*='resume-list']",
    "[class*='candidate-list']",
    "[class*='talent-list']",
    "table",
]
_ZP_TALENT_ITEMS = [
    ".search-resume-item-wrap",
    ".search-resume-item",
    ".resume-item__content",
    ".resume-card",
    ".candidate-card",
    ".talent-card",
    ".resume-item",
    ".candidate-item",
    ".talent-item",
    "[class*='resume'][class*='item']",
    "[class*='candidate'][class*='item']",
]
_ZP_TALENT_LOADING = ["text=加载中", "text=Loading", ".loading", ".k-loading", ".el-loading-mask"]
_ZP_TALENT_EMPTY = ["text=暂无数据", "text=暂无人才", "text=暂无简历", "text=没有找到", "text=无搜索结果", ".empty", ".no-data", ".no-result"]
_ZP_TALENT_API_DENY = re.compile(r"(?:job/list|getjoblist|company|position|commercial|notice|asset|im/|/menu|/job/)", re.I)
_ZP_TALENT_API_HINT = re.compile(r"(?:resume|candidate|talent|search)", re.I)
_ZP_RESUME_NAME = ("name", "userName", "realName", "showName", "姓名")
_ZP_RESUME_TITLE = ("currentJob", "currentPosition", "expectPosition", "expect_position",
                    "intentionJob", "desiredTitle", "求职意向", "意向职位")
_ZP_RESUME_CITY = ("workCity", "expectCity", "city", "currentCity", "所在城市", "意向城市")
_ZP_RESUME_EXP = ("workYears", "workYear", "experience", "yearsOfExp", "工作经验", "工龄")
_ZP_RESUME_EDU = ("eduLevel", "education", "学历")
_ZP_RESUME_MAJOR = ("major", "majorName", "专业")
_ZP_RESUME_SALARY = ("salary", "salaryDesc", "expectSalary", "salaryRange", "期望薪资")
_ZP_RESUME_ID = ("resumeNumber", "resumeId", "resume_id", "resumeNo", "userId", "user_id", "candidateId", "candidate_id")
_ZP_RESUME_DETAIL = ("resumeUrl", "detailUrl", "url", "viewUrl")
_ZP_RESUME_SUMMARY = ("summary", "selfEvaluation", "introduction", "自我评价", "introduce")
_ZP_COMPANY_OR_JOB_KEYS = {
    "companyname", "company_name", "companyfullname", "company_full_name",
    "orgname", "org_name", "jobname", "job_name", "jobtitle", "job_title",
    "positionname", "position_name", "positionid", "position_id",
    "jobnumber", "job_number", "recruitnumber", "recruit_number",
}
_ZP_RESUME_MARKER_KEYS = {
    "resumenumber", "resumeid", "resume_id", "resumeno", "resumeurl",
    "resume_url", "resumename", "resume_name", "candidateid",
    "candidate_id", "expectposition", "expect_position", "currentposition",
    "current_job", "selfevaluation", "workyears", "workyear", "edulevel",
}


def _zp_pick(item: dict, *keys: str) -> str:
    kl = {str(k).lower(): v for k, v in item.items()}
    for k in keys:
        v = kl.get(k.lower())
        if v not in (None, "", []):
            return str(v).strip()
    return ""


def _zp_likely_company_name(value: str) -> bool:
    text = clean(value)
    if not text:
        return False
    return bool(re.search(r"(有限公司|股份公司|集团|公司|中心|工厂|厂|店|商行|贸易|供应链|物流|物业|科技|餐饮|服饰|鞋业|五金)$", text))


def _zp_item_looks_like_resume(item: dict) -> bool:
    keys = {str(k).lower() for k in item.keys()}
    name = _zp_pick(item, *_ZP_RESUME_NAME)
    title = _zp_pick(item, *_ZP_RESUME_TITLE)
    detail = _zp_pick(item, *_ZP_RESUME_DETAIL)
    profile_signals = sum(
        1 for v in (
            _zp_pick(item, *_ZP_RESUME_EXP),
            _zp_pick(item, *_ZP_RESUME_EDU),
            _zp_pick(item, *_ZP_RESUME_MAJOR),
            _zp_pick(item, *_ZP_RESUME_SALARY),
            _zp_pick(item, *_ZP_RESUME_SUMMARY),
        )
        if v
    )
    has_resume_marker = bool(keys & _ZP_RESUME_MARKER_KEYS)
    has_resume_url = bool(detail and re.search(r"(resume|candidate|cv)", detail, re.I))
    looks_company_or_job = bool(keys & _ZP_COMPANY_OR_JOB_KEYS) or _zp_likely_company_name(name)
    if looks_company_or_job and not (has_resume_marker or has_resume_url):
        return False
    return bool(has_resume_marker or has_resume_url or (name and (title or profile_signals >= 2)))


def _zp_talent_entry(candidate: dict, raw_data: dict, keyword: str) -> dict:
    return {
        "platform": "zhaopin_resume",
        "platform_resume_id": candidate.get("platform_resume_id", ""),
        "name_masked": candidate.get("name_masked", ""),
        "desired_title": candidate.get("desired_title", ""),
        "city": candidate.get("city", ""),
        "experience": candidate.get("experience", ""),
        "education": candidate.get("education", ""),
        "major": candidate.get("major", ""),
        "salary_expectation": candidate.get("salary_expectation", ""),
        "source_url": candidate.get("source_url", ""),
        "resume_download_url": candidate.get("resume_download_url", ""),
        "raw_summary": candidate.get("raw_summary", ""),
        "raw_data": raw_data,
        "source_type": _ZP_TALENT_SOURCE_TYPE,
        "consent_status": _ZP_TALENT_CONSENT,
        "permission_note": _ZP_TALENT_PERMISSION,
        "status": "new",
        "notes": f"keyword={keyword}" if keyword else "",
    }


def _zp_talent_text_for_filter(item: dict, title: str, summary: str, major: str, experience: str) -> str:
    return _norm_value([
        title,
        summary,
        major,
        experience,
        _zp_pick(item, "skills", "skillTags", "tags", "labels", "recentWork", "recentPosition", "workExperience"),
    ])


def parse_zhaopin_resume_items(items: list[dict], *, fallback_url: str = "", keyword: str = "") -> list[dict]:
    """从智联 RP 接口拿到的 list[dict] 抽出 talent payload。
    fallback_url：当 item 内没有详情链接时落回的页面 URL（搜索页）。"""
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not _zp_item_looks_like_resume(item):
            continue
        rid = _zp_pick(item, *_ZP_RESUME_ID)
        name = _zp_pick(item, *_ZP_RESUME_NAME)
        title = _zp_pick(item, *_ZP_RESUME_TITLE)
        if not (rid or name or title):
            continue
        summary = _zp_pick(item, *_ZP_RESUME_SUMMARY)[:2000]
        major = _zp_pick(item, *_ZP_RESUME_MAJOR)
        experience = _zp_pick(item, *_ZP_RESUME_EXP)
        filter_text = _zp_talent_text_for_filter(item, title, summary, major, experience)
        if filter_text and not has_crossborder([filter_text]):
            continue
        detail = _zp_pick(item, *_ZP_RESUME_DETAIL)
        if detail:
            source_url = urljoin("https://rd6.zhaopin.com/", detail)
        else:
            source_url = fallback_url or "https://rd6.zhaopin.com/"
        out.append(_zp_talent_entry({
            "platform_resume_id": rid,
            "name_masked": name,
            "desired_title": title,
            "city": _zp_pick(item, *_ZP_RESUME_CITY),
            "experience": experience,
            "education": _zp_pick(item, *_ZP_RESUME_EDU),
            "major": major,
            "salary_expectation": _zp_pick(item, *_ZP_RESUME_SALARY),
            "source_url": source_url,
            "raw_summary": summary,
        }, item, keyword))
    return out


def _find_resume_lists(obj, depth: int = 0) -> list[list[dict]]:
    """递归找真正像简历/候选人的 list[dict]，避免把公司/职位 JSON 当人才。"""
    if depth > 6:
        return []
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        sample = [x for x in obj[:5] if isinstance(x, dict)]
        if any(_zp_item_looks_like_resume(x) for x in sample):
            return [obj]
        return []
    found: list[list[dict]] = []
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_find_resume_lists(v, depth + 1))
    if isinstance(obj, list):
        for v in obj[:30]:
            found.extend(_find_resume_lists(v, depth + 1))
    return found


async def _zhaopin_talent_login_state(page) -> tuple[bool, str]:
    if page.is_closed():
        return False, "page_closed"
    url = page.url.lower()
    if "passport.zhaopin.com" in url or "/org/login" in url:
        return False, f"login_url:{page.url}"
    try:
        text = await page.locator("body").inner_text(timeout=1500)
    except Exception:
        text = ""
    compact = clean(text)
    if re.search(r"(企业登录|智联招聘-登录|登录智联招聘|扫码登录|账号登录|短信登录|验证码登录|手机号|短信验证码|获取验证码|请输入密码)", compact):
        return False, "login_panel"
    if re.search(r"(搜索人才|推荐人才|潜在人才|人才管理|人才搜索|职位中心|退出登录)", compact):
        return True, "rd_hint"
    return True, "no_login_marker"


async def ensure_zhaopin_talent_login(page, captcha_timeout: int) -> bool:
    logged_in, reason = await _zhaopin_talent_login_state(page)
    if logged_in:
        return True
    captcha_timeout = max(captcha_timeout, 600)
    print(f"[LOGIN] 智联企业端未登录或登录态失效 ({reason})，请在打开的页面完成登录。")
    t0 = time.time()
    while time.time() - t0 < captcha_timeout:
        if page.is_closed():
            print("[LOGIN] 智联企业端页面已关闭，停止当前页采集。")
            return False
        sec_hit, sec_token = await check_security_page(page)
        if sec_hit:
            print(f"[LOGIN] 智联企业端命中安全验证 ({sec_token})，请先手动通过。")
            await wait_captcha(page, min(captcha_timeout, 180))
        logged_in, reason = await _zhaopin_talent_login_state(page)
        if logged_in:
            print("[LOGIN] 智联企业端登录态检查通过，继续采集。")
            return True
        await asyncio.sleep(2)
    print(f"[LOGIN] 智联企业端登录等待超时 ({captcha_timeout}s)，跳过当前页。")
    return False


async def open_zhaopin_talent_search(page, captcha_timeout: int) -> bool:
    logged_in, _ = await _zhaopin_talent_login_state(page)
    if not logged_in:
        if not await ensure_zhaopin_talent_login(page, captcha_timeout):
            return False
    try:
        await page.goto(ZHAOPIN_RESUME_HOME, timeout=30_000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        await rnd_delay(2, 4)
    except Exception as exc:
        print(f"[ERROR] 打开智联搜索人才入口失败: {exc}")
        return False
    if "/404" in page.url:
        print(f"[ERROR] 智联搜索人才入口返回 404: {page.url}")
        return False
    sec_hit, sec_token = await check_security_page(page)
    if sec_hit:
        print(f"[VERIFY] 智联搜索人才入口被安全验证拦截 ({sec_token})，等待人工处理。")
        if not await wait_captcha(page, captcha_timeout):
            return False
    if await check_captcha(page):
        if not await wait_captcha(page, captcha_timeout):
            return False
    if not await ensure_zhaopin_talent_login(page, captcha_timeout):
        return False
    return True


async def _click_zhaopin_resume_search(page) -> bool:
    for sel in [
        "button.keyword-input-tag__btn",
        ".keyword-input-tag__btn",
        "button:has-text('搜索')",
        "button:has-text('搜 索')",
        "button:has-text('找人才')",
        ".k-button:has-text('搜索')",
        ".k-button:has-text('搜 索')",
        "[role='button']:has-text('搜索')",
        "[role='button']:has-text('搜 索')",
    ]:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=2000)
                await rnd_delay(2, 3)
                return True
        except Exception:
            continue
    for text in ("搜索", "搜 索", "查询", "找人才"):
        try:
            btn = page.get_by_text(text, exact=True).first
            if await btn.count() > 0:
                await btn.click(timeout=2000)
                await rnd_delay(2, 3)
                return True
        except Exception:
            continue
    return False


async def _drive_zhaopin_resume_search(page, keyword: str) -> bool:
    """Drive RD search like a user: type keyword, then click the search button."""
    if not keyword:
        return False
    deadline = time.time() + 12
    last_title = ""
    while time.time() < deadline:
        logged_in, reason = await _zhaopin_talent_login_state(page)
        if not logged_in:
            print(f"[LOGIN] 智联企业端已跳转到登录页 ({reason})，请先登录后再开始采集。")
            return False
        try:
            last_title = await page.title()
        except Exception:
            last_title = ""
        for sel in _ZP_TALENT_INPUT:
            try:
                loc = page.locator(sel).first
                if await loc.count() <= 0:
                    continue
                await loc.wait_for(state="visible", timeout=800)
                await loc.scroll_into_view_if_needed()
                try:
                    await loc.fill(keyword, timeout=3000)
                except Exception:
                    await loc.click(timeout=3000, force=True)
                    await loc.fill(keyword, timeout=3000)
                await rnd_delay(0.4, 1.0)
                if not await _click_zhaopin_resume_search(page):
                    await loc.press("Enter")
                    await rnd_delay(2, 3)
                return True
            except Exception:
                continue
        for sel in _ZP_TALENT_CLICK_TARGETS:
            try:
                target = page.locator(sel).first
                if await target.count() <= 0:
                    continue
                await target.wait_for(state="visible", timeout=800)
                await target.scroll_into_view_if_needed()
                await target.hover()
                await rnd_delay(0.3, 0.8)
                await target.click(timeout=3000)
                await page.keyboard.press("Control+A")
                await page.keyboard.type(keyword, delay=random.randint(20, 60))
                await rnd_delay(0.4, 1.0)
                if not await _click_zhaopin_resume_search(page):
                    await page.keyboard.press("Enter")
                    await rnd_delay(2, 3)
                return True
            except Exception:
                continue
        await asyncio.sleep(1)
    print(f"[ERROR] 智联搜索人才输入框未找到: url={page.url} title={last_title}")
    try:
        body_head = clean(await page.locator("body").inner_text(timeout=1500))[:500]
        print(f"[INSPECT-PAGE] body 前 500 字: {body_head}")
        inputs = await page.locator("input,textarea,[contenteditable=true]").evaluate_all(
            """els => els.slice(0, 30).map((e, i) => ({
              i,
              tag: e.tagName,
              type: e.type || '',
              placeholder: e.getAttribute('placeholder') || '',
              text: (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
              cls: String(e.className || '').slice(0, 80),
              visible: !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)
            }))"""
        )
        print(f"[INSPECT-PAGE] inputs: {json.dumps(inputs, ensure_ascii=False)}")
    except Exception as exc:
        print(f"[INSPECT-PAGE] 输入框诊断失败: {exc}")
    return False


async def search_zhaopin_talent_keyword(page, keyword: str, captcha_timeout: int) -> bool:
    if not await ensure_zhaopin_talent_login(page, captcha_timeout):
        return False
    if not await _drive_zhaopin_resume_search(page, keyword):
        return False
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    await rnd_delay(1.5, 2.5)
    sec_hit, sec_token = await check_security_page(page)
    if sec_hit:
        print(f"[VERIFY] 智联搜索人才结果页被安全验证拦截 ({sec_token})，停止当前关键词。")
        return False
    if await check_captcha(page):
        if not await wait_captcha(page, captcha_timeout):
            return False
    return True


async def wait_zhaopin_talent_results(page, keyword: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        list_visible = await _has_visible(page, _ZP_TALENT_LIST)
        empty_visible = await _has_visible(page, _ZP_TALENT_EMPTY)
        loading_visible = await _has_visible(page, _ZP_TALENT_LOADING)
        if (list_visible or empty_visible) and not loading_visible:
            return
        print(f"[WAIT] 智联搜索人才结果加载中 keyword={keyword!r} url={page.url}")
        await asyncio.sleep(1)


async def _goto_zhaopin_resume_page(page, pg: int) -> bool:
    """智联人才点击式翻页：优先在翻页器容器（用户提供的 XPath）内点页码 / 下一页，并确认列表刷新。

    仅在 pg>1 时调用。成功返回 True；找不到可点击控件（通常已到末页）返回 False。
    """
    if pg <= 1:
        return True
    items_sel = ",".join(_ZP_TALENT_ITEMS)
    try:
        before = await page.locator(items_sel).first.inner_text(timeout=1500)
    except Exception:
        before = ""

    candidates = []
    pager = page.locator(ZHAOPIN_TALENT_PAGER).first
    try:
        if await pager.count() > 0:
            for sub in (f"li:text-is('{pg}')", f"a:text-is('{pg}')", f"button:text-is('{pg}')",
                        ".el-pagination__next", "button:has-text('下一页')", "a:has-text('下一页')",
                        "[class*='next']"):
                candidates.append(pager.locator(sub).first)
            # 该 XPath 本身可能就是“下一页”按钮，作为兜底直接点击容器。
            candidates.append(pager)
    except Exception:
        pass
    # 全页兜底：页码文本 / 通用下一页按钮。
    for sel in (f"a:text-is('{pg}')", f"button:text-is('{pg}')", f"li:text-is('{pg}')",
                ".el-pagination__next", ".k-pagination-next",
                "button:has-text('下一页')", "a:has-text('下一页')"):
        candidates.append(page.locator(sel).first)

    for target in candidates:
        try:
            if await target.count() == 0 or not await target.is_visible(timeout=400):
                continue
            cls = (await target.get_attribute("class")) or ""
            aria = await target.get_attribute("aria-disabled")
            if aria == "true" or re.search(r"disabled|is-disabled", cls):
                continue
            await target.scroll_into_view_if_needed()
            await asyncio.sleep(random.uniform(0.2, 0.6))
            await target.click(timeout=4000)
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    after = await page.locator(items_sel).first.inner_text(timeout=1000)
                except Exception:
                    after = ""
                if after and after != before:
                    return True
                await asyncio.sleep(0.6)
            # 点过了但未检测到明显变化，交给上层“翻页未推进/全部重复”去重逻辑判定。
            return True
        except Exception:
            continue
    return False


def _zhaopin_talent_api_candidate(url: str) -> bool:
    text = (url or "").lower()
    if _ZP_TALENT_API_DENY.search(text):
        return False
    return bool(_ZP_TALENT_API_HINT.search(text))


def parse_zhaopin_talent_dom_text(text: str, keyword: str, source_url: str) -> dict | None:
    normalized = clean(text)
    if not normalized:
        return None
    if re.search(r"(有限公司|集团|公司).{0,20}(招聘|职位|薪资|岗位)", normalized):
        return None
    if not has_crossborder([normalized]):
        return None
    name = re.search(r"(?:姓名|候选人)[:：]?\s*([\u4e00-\u9fa5A-Za-z*]{1,12})", normalized)
    if not name:
        name = re.search(r"^([\u4e00-\u9fa5A-Za-z*]{1,12}(?:先生|女士|同学)?)\s", normalized)
    title = re.search(r"(?:求职意向|意向职位|期望职位|当前岗位|最近职位)[:：]?\s*([^|，,。]{2,40}?)(?=\s*(?:城市|现居住地|工作经验|经验|学历|期望薪资|薪资|$))", normalized)
    city = re.search(r"(?:泉州|厦门|福州|深圳|广州|杭州|上海|北京|义乌|东莞|晋江|石狮|南安|丰泽|鲤城|洛江|惠安|南宁)", normalized)
    if not title:
        city_prefix = city.group(0) if city else ""
        city_part = re.escape(city_prefix) + r"\s+" if city_prefix else r"(?:泉州|厦门|福州|深圳|广州|杭州|上海|北京|义乌|东莞|晋江|石狮|南安|丰泽|鲤城|洛江|惠安|南宁)?\s*"
        title = re.search(rf"期望[:：]\s*{city_part}([^|，,。0-9]{{2,40}}?)(?=\s*(?:\d|面议|[1-9]))", normalized)
    if not title:
        title = re.search(r"(跨境电商运营|亚马逊运营|外贸业务员|外贸销售|海外仓|供应链|品牌出海|Amazon运营)", normalized, re.I)
    education = re.search(r"(博士|硕士|研究生|本科|大专|中专|高中)", normalized)
    experience = re.search(r"(?:\d+\s*-\s*\d+年|\d+年以上|\d+年经验|\d+年|应届|无经验|经验不限)", normalized)
    salary = re.search(r"(?:\d+(?:\.\d+)?\s*[Kk千]\s*-\s*\d+(?:\.\d+)?\s*[Kk千万]?|\d+\s*-\s*\d+\s*[Kk千万]?|面议|期望薪资[:：]?\s*[^|，,。]{2,20})", normalized)
    if not (name or title or experience or education):
        return None
    return _zp_talent_entry({
        "platform_resume_id": _job51_resume_id(source_url),
        "name_masked": name.group(1) if name else "",
        "desired_title": title.group(1) if title else "",
        "city": city.group(0) if city else "",
        "experience": experience.group(0) if experience else "",
        "education": education.group(0) if education else "",
        "salary_expectation": salary.group(0) if salary else "",
        "source_url": source_url,
        "raw_summary": normalized[:2000],
    }, {"keyword": keyword, "card_text": normalized[:1200], "source_url": source_url}, keyword)


async def parse_zhaopin_talent_dom(page, keyword: str) -> list[dict]:
    entries: list[dict] = []
    try:
        cards = await page.evaluate(
            """() => {
              const pick = (selectors) => {
                for (const sel of selectors) {
                  const items = Array.from(document.querySelectorAll(sel))
                    .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length));
                  if (items.length) return items;
                }
                return [];
              };
              const nodes = pick([
                '.search-resume-item-wrap',
                '.search-resume-item',
                '.resume-item__content',
                '.resume-card',
                '.candidate-card',
                '.talent-card',
                '.resume-item',
                '.candidate-item',
                '.talent-item'
              ]);
              return nodes.slice(0, 80).map((el, index) => {
                const link = el.querySelector("a[href*='resume'],a[href*='candidate'],a[href*='talent'],a[href]");
                return {
                  index,
                  text: String(el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
                  href: link ? (link.getAttribute('href') || link.href || '') : ''
                };
              });
            }"""
        )
    except Exception:
        cards = []
    for card in cards:
        index = int(card.get("index") or 0)
        text = card.get("text") or ""
        href = card.get("href") or ""
        source_url = urljoin(page.url, href) if href else f"{page.url}#zhaopin-talent-{index}"
        entry = parse_zhaopin_talent_dom_text(text, keyword, source_url)
        if entry:
            entries.append(entry)
    return _dedupe_talent_entries(entries)


async def scrape_zhaopin_resume_page(page, capture_data: list[dict], keyword: str, pg: int,
                                     captcha_timeout: int, inspect: bool = False) -> list[dict]:
    """智联企业端搜索人才：进入页 -> 输入关键词点击搜索 -> API 优先，DOM 兜底。
    登录/验证码/安全验证处理参考智联公司采集。"""
    if pg <= 1:
        if not await open_zhaopin_talent_search(page, captcha_timeout):
            return []
        capture_data.clear()
        if not await search_zhaopin_talent_keyword(page, keyword, captcha_timeout):
            return []
    else:
        capture_data.clear()
        if not await _goto_zhaopin_resume_page(page, pg):
            print(f"[INFO] 智联人才未找到可点击的翻页控件（第 {pg} 页，通常已到末页），停止当前关键词")
            return []
        sec_hit, sec_token = await check_security_page(page)
        if sec_hit:
            print(f"[VERIFY] 智联搜索人才翻页后被安全验证拦截 ({sec_token})，停止当前关键词。")
            return []
        if await check_captcha(page):
            if not await wait_captcha(page, captcha_timeout):
                return []

    if not await ensure_zhaopin_talent_login(page, captcha_timeout):
        return []
    await wait_zhaopin_talent_results(page, keyword)
    await rnd_delay(1, 2)

    fallback_url = page.url

    if inspect:
        print(f"\n[INSPECT-API] 拦截到 {len(capture_data)} 个 JSON 响应:")
        for cap in capture_data[-16:]:
            body = cap.get("body")
            allowed = _zhaopin_talent_api_candidate(cap.get("url", ""))
            if isinstance(body, dict):
                list_field = next((k for k, v in body.items() if isinstance(v, list) and v), None)
                print(f"  URL : {cap['url']}  talent_api={allowed}")
                print(f"  顶层: {list(body.keys())[:12]}")
                if list_field:
                    sample = body[list_field][0] if body[list_field] else {}
                    sample_keys = list(sample.keys())[:14] if isinstance(sample, dict) else []
                    print(f"  列表: {list_field!r} ({len(body[list_field])}条) 首条键={sample_keys}")
            elif isinstance(body, list) and body:
                print(f"  URL : {cap['url']}  talent_api={allowed}")
                print(f"  数组: {len(body)} 条，首条键={list(body[0].keys())[:14] if isinstance(body[0], dict) else []}")

    # 智联企业端 search/list 与 resume/detail JSON 体很深，先按页面卡片解析；
    # Inspect 仍会打印真实接口，后续按字段稳定后再补精确 API parser。
    results = await parse_zhaopin_talent_dom(page, keyword)
    print(f"[INFO] 智联人才 DOM 解析 {len(results)} 条 keyword={keyword!r}")
    return _dedupe_talent_entries(results)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _open_browser_context(playwright, platform: str):
    cdp_url = (
        os.environ.get("COMPANYLEADS_CDP_URL")
        or os.environ.get("QCWY_CDP_URL")
        or os.environ.get("CHROME_CDP_URL")
    )
    if not cdp_url:
        cdp_url = _runtime_cdp_url()

    cdp_port = os.environ.get("COMPANYLEADS_CHROME_DEBUG_PORT") or os.environ.get("QCWY_CHROME_DEBUG_PORT")
    if not cdp_url and cdp_port:
        cdp_url = f"http://127.0.0.1:{cdp_port}"
    if not cdp_url and platform in {"51job", "51job_talent"}:
        cdp_url = "http://127.0.0.1:9222"

    if cdp_url:
        try:
            if platform in {"51job", "51job_talent"}:
                await _ensure_chrome_cdp(cdp_url)
            browser = await playwright.chromium.connect_over_cdp(cdp_url)
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            print(f"[BROWSER] attached over CDP: {cdp_url}")
            return ctx, False
        except Exception as exc:
            strict_cdp = os.environ.get("COMPANYLEADS_REQUIRE_CDP") == "1"
            print(f"[BROWSER] CDP attach failed: {cdp_url} ({exc})")
            if strict_cdp or platform in {"51job", "51job_talent"}:
                raise BrowserSessionError(
                    "51job requires your controlled Chrome CDP session. Start Chrome with remote debugging and retry. "
                    f"CDP was not reachable: {cdp_url}"
                ) from exc
            print("[BROWSER] falling back to local persistent profile. Set COMPANYLEADS_REQUIRE_CDP=1 to fail instead.")

    if platform in {"51job", "51job_talent"}:
        raise BrowserSessionError(
            "51job requires a controlled Chrome CDP session. Start Chrome with --remote-debugging-port "
            "or set COMPANYLEADS_CDP_URL / QCWY_CHROME_DEBUG_PORT before running."
        )

    ctx = await playwright.chromium.launch_persistent_context(
        USER_DATA_DIR, headless=False, channel="chrome",
    )
    print(f"[BROWSER] launched local persistent profile: {USER_DATA_DIR}")
    return ctx, True


async def scrape(platform: str, keywords: list[str], max_pages: int, dry_run: bool,
                 captcha_timeout: int, inspect: bool = False,
                 # 列表 / 详情默认等待（feature 引入）
                 delay_min: float = 8.0, delay_max: float = 15.0,
                 detail_delay_min: float = 10.0, detail_delay_max: float = 20.0,
                 max_items: int = 0,
                 per_keyword_limit: int = 0,
                 # list 层节奏：每 batch_size 个 (kw,pg) 项后冷却（HEAD V 轮通用，默认 OFF）
                 batch_size: int = 0, item_delay_lo: float = 2.0, item_delay_hi: float = 5.0,
                 batch_delay_lo: float = 0.0, batch_delay_hi: float = 0.0,
                 stop_on_captcha: bool = False, post_captcha_multiplier: float = 3.0,
                 # enrich 层节奏：51job 详情批量打开冷却（沿用 qzrc enrich 命名 + 默认值）
                 enrich_batch_size: int = 10,
                 enrich_batch_delay_lo: float = 180.0,
                 enrich_batch_delay_hi: float = 480.0) -> None:
    """采集节奏双层模型：
        list 层（batch_size>0 + batch_delay>0 时启用）：每 batch_size 个 (kw,pg) 项后随机冷却 batch_delay；命中验证码立即停批。
        enrich 层（51job 详情）：每 enrich_batch_size 个详情后随机冷却 enrich_batch_delay。"""
    # 51job / 51job_talent 内置「中等保守」节奏：比现状稳、比保守版快；
    # 不暴露到侧边栏，直接覆盖传入参数（qzrc / 智联不受影响）。
    if platform in {"51job", "51job_talent"}:
        delay_min, delay_max = 2.0, 4.0
        detail_delay_min, detail_delay_max = 5.0, 9.0
        enrich_batch_size = 5
        enrich_batch_delay_lo, enrich_batch_delay_hi = 60.0, 150.0
        stop_on_captcha = True
        print("[51JOB-PACING] 中等节奏：list 2-4s，detail 5-9s，每 5 条冷却 60-150s，命中验证即停")
    pacing_enabled = batch_size > 0 and batch_delay_lo > 0
    print(
        f"[INFO] platform={platform} keywords={keywords} max_pages={max_pages} "
        f"dry_run={dry_run} captcha_timeout={captcha_timeout} "
        f"delay={delay_min}-{delay_max}s detail_delay={detail_delay_min}-{detail_delay_max}s "
        f"max_items={max_items or 'unlimited'} per_keyword_limit={per_keyword_limit or 'unlimited'} "
        f"batch={batch_size}/{batch_delay_lo}-{batch_delay_hi}s"
    )
    if pacing_enabled:
        print(f"[CFG]  采集节奏：每 {batch_size} 个 (kw,pg) 暂停 {batch_delay_lo:.0f}-{batch_delay_hi:.0f}s，"
              f"单项 {item_delay_lo:.0f}-{item_delay_hi:.0f}s，"
              f"{'命中验证码即终止整个 run' if stop_on_captcha else f'命中后下批 ×{post_captcha_multiplier:.1f}'}")

    is_resume_mode = platform in {"zhaopin_resume", "51job_talent"}
    login_policy = _login_policy(platform)
    total_pages = max(1, len(keywords) * max_pages)
    pages_done = 0
    emit_progress(
        "start",
        f"{platform} 采集启动",
        current=0,
        total=total_pages,
        items_total=0,
    )
    async with async_playwright() as p:
        ctx, owns_context = await _open_browser_context(p, platform)
        page = await ctx.new_page()

        # 简历模式注册 XHR/JSON 抓包
        capture_data: list[dict] = []
        if is_resume_mode:
            async def _route_handler(route):
                req = route.request
                if req.resource_type not in ("xhr", "fetch"):
                    await route.continue_()
                    return
                if platform == "zhaopin_resume" and not _zhaopin_talent_api_candidate(req.url):
                    await route.continue_()
                    return
                try:
                    response = await route.fetch(timeout=15_000)
                    ct = (response.headers.get("content-type") or "").lower()
                    if "json" in ct:
                        body_bytes = await response.body()
                        try:
                            capture_data.append({"url": req.url, "body": json.loads(body_bytes.decode("utf-8", errors="ignore"))})
                        except Exception:
                            pass
                    await route.fulfill(response=response)
                except Exception:
                    await route.continue_()
            await page.route("**/*", _route_handler)

        all_entries: list[dict] = []
        seen_keys: set[str] = set()
        stop_requested = False
        items_in_batch = 0
        captcha_hit_in_batch = False
        enriched_since_pause = 0
        realtime_upsert_ok = 0
        realtime_upsert_fail = 0

        for kw in keywords:
            if stop_requested:
                break
            keyword_count = 0
            kw_seen_keys: set[str] = set()
            for pg in range(1, max_pages + 1):
                if stop_requested:
                    break
                print(f"[SCRAPE] {platform} keyword={kw!r} page={pg}")
                emit_progress(
                    "page",
                    f"{platform} 第 {pg} 页",
                    current=min(pages_done + 1, total_pages),
                    total=total_pages,
                    current_keyword=kw,
                    current_page=pg,
                    items_total=len(all_entries),
                )
                if page.is_closed():
                    print("[STOP] 浏览器页面已关闭，提前结束任务。")
                    stop_requested = True
                    break
                try:
                    if platform == "51job":
                        entries = await scrape_51job_page(
                            page, kw, pg, captcha_timeout,
                            inspect=inspect,
                            delay_min=delay_min,
                            delay_max=delay_max,
                        )
                    elif platform == "zhaopin":
                        entries = await scrape_zhaopin_page(page, kw, pg, captcha_timeout, inspect=inspect)
                    elif platform == "51job_talent":
                        entries = await scrape_51job_talent_page(
                            page, capture_data, kw, pg, captcha_timeout, inspect=inspect
                        )
                    else:   # zhaopin_resume
                        entries = await scrape_zhaopin_resume_page(
                            page, capture_data, kw, pg, captcha_timeout, inspect=inspect
                        )
                except Exception as exc:
                    if page.is_closed() or "Target page" in str(exc) or "Target browser" in str(exc):
                        print("[STOP] 浏览器已关闭，提前结束任务。")
                        stop_requested = True
                        break
                    print(f"[ERROR] {exc}")
                    entries = []

                # 列表页验证码检测（统一用 check_security_page —— 涵盖 EdgeOne / 滑块 / Cloudflare）
                # 51job / 51job_talent 即使未启用 list 层 pacing，也要检测列表页验证并按 stop_on_captcha 停止。
                if pacing_enabled or platform in {"51job", "51job_talent"}:
                    sec_hit, sec_token = await check_security_page(page)
                    if sec_hit:
                        if platform in {"51job", "51job_talent"}:
                            print(f"[51JOB-VERIFY-HOLD] 列表页命中安全验证 ({sec_token})，停止任务，保留验证页等待人工处理")
                        else:
                            print(f"[CAPTCHA] {platform} keyword={kw!r} page={pg} 命中安全验证页 ({sec_token})，停批")
                        captcha_hit_in_batch = True
                        pages_done += 1
                        emit_progress(
                            "page_done",
                            "命中安全验证，已停批",
                            current=min(pages_done, total_pages),
                            total=total_pages,
                            current_keyword=kw,
                            current_page=pg,
                            items_total=len(all_entries),
                        )
                        if stop_on_captcha:
                            stop_requested = True
                        break

                if not entries:
                    print(f"[INFO] 第 {pg} 页无结果，跳出当前关键词")
                    pages_done += 1
                    emit_progress(
                        "page_done",
                        "本页无结果",
                        current=min(pages_done, total_pages),
                        total=total_pages,
                        current_keyword=kw,
                        current_page=pg,
                        items_total=len(all_entries),
                    )
                    break

                # ── 翻页推进检测 + 去重（修复"翻页直接跳到末页/只采到约15条"问题）──
                # 翻页 bug 表现：第 N 页直接跳回首页或末页，拿到的与本关键词前面页完全相同。
                # 1) 用关键词内已见键判断翻页是否真的“推进”：若本页全部与前页重复，则停当前关键词；
                # 2) 用全局 seen_keys 跨关键词去重，避免对同一条线索重复补全/入库（降低反爬暴露）。
                try:
                    cur_url = page.url
                except Exception:
                    cur_url = ""
                cur_keys = [_entry_key(e) for e in entries]
                new_for_kw = [k for k in cur_keys if k not in kw_seen_keys]
                if pg > 1 and cur_keys and not new_for_kw:
                    print(
                        f"[PAGINATION] {platform} kw={kw!r} page={pg} url={cur_url} "
                        f"本页 {len(cur_keys)} 条全部与本关键词前页重复，判定翻页未推进"
                        f"（疑似跳回首页/末页），停止当前关键词"
                    )
                    pages_done += 1
                    emit_progress(
                        "page_done",
                        "翻页未推进（全部重复），已停止该关键词",
                        current=min(pages_done, total_pages),
                        total=total_pages,
                        current_keyword=kw,
                        current_page=pg,
                        items_total=len(all_entries),
                    )
                    break
                kw_seen_keys.update(cur_keys)
                fresh_entries: list[dict] = []
                dup_global = 0
                for _e in entries:
                    _k = _entry_key(_e)
                    if _k in seen_keys:
                        dup_global += 1
                        continue
                    seen_keys.add(_k)
                    fresh_entries.append(_e)
                print(
                    f"[PAGINATION] {platform} kw={kw!r} page={pg} url={cur_url} "
                    f"本页 {len(cur_keys)} 条 / 关键词内新增 {len(new_for_kw)} / "
                    f"全局新增 {len(fresh_entries)} / 全局重复 {dup_global}"
                )
                # 仅保留全局新线索用于补全/入库/计数；若本页全为跨关键词重复，entries 为空，
                # 不会浪费详情补全，流程会自然带着节奏延时翻到下一页。
                entries = fresh_entries

                if max_items > 0:
                    remaining = max_items - len(all_entries)
                    if remaining <= 0:
                        stop_requested = True
                        break
                    entries = entries[:remaining]
                if per_keyword_limit > 0:
                    remaining_keyword = per_keyword_limit - keyword_count
                    if remaining_keyword <= 0:
                        break
                    entries = entries[:remaining_keyword]

                for entry in entries:
                    raw = entry.get("raw_data") if isinstance(entry.get("raw_data"), dict) else {}
                    raw.setdefault("keyword", kw)
                    raw.setdefault("search_keyword", kw)
                    raw.setdefault("page", pg)
                    entry["raw_data"] = raw
                    entry.setdefault("search_keyword", kw)
                    entry.setdefault("search_keywords", kw)
                    # 登录上下文（仅写 raw_data，不新增数据库字段）：
                    # optional=公司客户公开采集；login_wall_hit 默认 False，enrich 命中登录墙时置 True。
                    raw.setdefault("login_policy", login_policy)
                    raw.setdefault("public_capture", login_policy == "optional")
                    raw.setdefault("login_wall_hit", False)

                should_enrich_details = platform in {"51job", "zhaopin"} and (not dry_run or platform == "zhaopin")
                if should_enrich_details:
                    enriched_entries: list[dict] = []
                    for enrich_idx, entry in enumerate(entries, 1):
                        emit_progress(
                            "enrich",
                            f"{platform} 详情补全 {enrich_idx}/{len(entries)}",
                            current=min(pages_done + 1, total_pages),
                            total=total_pages,
                            current_keyword=kw,
                            current_page=pg,
                            items_total=len(all_entries) + enrich_idx - 1,
                        )
                        if platform == "51job":
                            entry = await enrich_51job(
                                page, entry,
                                captcha_timeout=min(captcha_timeout, 90),
                                delay_min=detail_delay_min,
                                delay_max=detail_delay_max,
                            )
                        else:
                            entry = await enrich_zhaopin(page, entry, captcha_timeout=min(captcha_timeout, 90))
                        enriched_entries.append(entry)
                        raw = entry.get("raw_data") if isinstance(entry.get("raw_data"), dict) else {}
                        if platform == "zhaopin" and raw.get("zhaopin_security_hold"):
                            captcha_hit_in_batch = True
                            stop_requested = True
                            print("[STOP] 智联详情页触发安全验证/操作频繁，已停止本轮任务，保留验证标签等待人工处理或冷却。")
                            break
                        if platform == "51job" and raw.get("job51_verify_hold"):
                            captcha_hit_in_batch = True
                            stop_requested = True
                            print("[51JOB-VERIFY-HOLD] 详情页触发反爬验证，已停止本轮任务，保留验证页等待人工处理，不再打开新详情。")
                            break
                        if not dry_run:
                            if push_one(entry, dry_run=False):
                                realtime_upsert_ok += 1
                            else:
                                realtime_upsert_fail += 1
                        await rnd_delay(detail_delay_min, detail_delay_max)
                        enriched_since_pause += 1
                        if (
                            platform in {"51job", "zhaopin"}
                            and enrich_batch_size > 0
                            and enriched_since_pause >= enrich_batch_size
                            and enrich_idx < len(entries)
                        ):
                            pause_seconds = random.uniform(enrich_batch_delay_lo, enrich_batch_delay_hi)
                            print(f"[ANTI-BOT] enrich_batch_size={enrich_batch_size}; pausing {pause_seconds:.1f}s before continuing")
                            await asyncio.sleep(pause_seconds)
                            enriched_since_pause = 0
                    entries = enriched_entries

                all_entries.extend(entries)
                keyword_count += len(entries)
                print(f"[INFO] 本页 {len(entries)} 条，累计 {len(all_entries)} 条")
                pages_done += 1
                emit_progress(
                    "page_done",
                    f"本页 {len(entries)} 条，累计 {len(all_entries)} 条",
                    current=min(pages_done, total_pages),
                    total=total_pages,
                    current_keyword=kw,
                    current_page=pg,
                    items_total=len(all_entries),
                )

                if max_items > 0 and len(all_entries) >= max_items:
                    print(f"[INFO] 已达到 max_items={max_items}，提前结束")
                    stop_requested = True
                    break
                if per_keyword_limit > 0 and keyword_count >= per_keyword_limit:
                    print(f"[INFO] keyword={kw!r} 已达到 per_keyword_limit={per_keyword_limit}")
                    break

                # ──── list 层节奏：单项间隔 + 每 batch_size 项后冷却 ────
                if pacing_enabled:
                    items_in_batch += 1
                    if items_in_batch >= batch_size:
                        cool = random.uniform(batch_delay_lo, batch_delay_hi)
                        if captcha_hit_in_batch:
                            cool *= post_captcha_multiplier
                        print(f"[REST] 本批已处理 {items_in_batch} 项，冷却 {cool:.0f}s "
                              f"(≈{cool/60:.1f} min){' (验证码后加倍)' if captcha_hit_in_batch else ''}")
                        await asyncio.sleep(cool)
                        items_in_batch = 0
                        captcha_hit_in_batch = False
                    else:
                        await rnd_delay(item_delay_lo, item_delay_hi)
                else:
                    await rnd_delay(delay_min, delay_max)

            # 跨关键词，如果有未消化的"批后冷却 ×3"需要做
            if pacing_enabled and captcha_hit_in_batch and not stop_on_captcha:
                cool = random.uniform(batch_delay_lo, batch_delay_hi) * post_captcha_multiplier
                print(f"[COOLDOWN] 关键词中断后冷却 {cool:.0f}s")
                await asyncio.sleep(cool)
                items_in_batch = 0
                captcha_hit_in_batch = False

        print(f"[INFO] 采集完成，共 {len(all_entries)} 条")
        emit_progress(
            "done",
            f"采集完成，共 {len(all_entries)} 条",
            current=total_pages,
            total=total_pages,
            items_total=len(all_entries),
            percent=100,
        )
        if platform in {"51job", "zhaopin"} and not dry_run:
            print(
                f"[SUMMARY] realtime upsert: {realtime_upsert_ok} ok / "
                f"{realtime_upsert_fail} failed; kept {len(all_entries)} entries in run summary"
            )
        if is_resume_mode:
            if platform == "51job_talent" and dry_run:
                print("Talent ingest dry-run; skipping API request")
            push_talents(all_entries, dry_run=dry_run)
            if platform == "51job_talent":
                print("前程无忧人才 crawl finished")
        elif platform in {"51job", "zhaopin"} and not dry_run:
            print("[SUMMARY] company entries were already upserted one by one; skip final batch push")
        else:
            push_all(all_entries, dry_run=dry_run)
        await page.close()
        if owns_context:
            await ctx.close()


def main():
    parser = argparse.ArgumentParser(description="公司线索爬虫 — 51job / 智联",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--platform", choices=["51job", "51job_talent", "zhaopin", "zhaopin_resume"], default="51job")
    parser.add_argument("--keywords", default="", help="逗号分隔关键词，不填用内置默认值")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--captcha-timeout", type=int, default=180, help="验证码人工处理等待秒数")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect", action="store_true",
                        help="打印拦截到的 JSON 接口 URL 与字段（zhaopin_resume）/ 卡片 a[href]（zhaopin）")
    # 列表 / 详情默认等待（feature 引入）
    parser.add_argument("--delay-min", type=float, default=8.0, help="列表页/翻页最小等待秒数（list pacing 未启用时的 fallback）")
    parser.add_argument("--delay-max", type=float, default=15.0, help="列表页/翻页最大等待秒数")
    parser.add_argument("--detail-delay-min", type=float, default=10.0, help="详情页最小等待秒数")
    parser.add_argument("--detail-delay-max", type=float, default=20.0, help="详情页最大等待秒数")
    parser.add_argument("--max-items", type=int, default=0, help="本次最多处理条数，0 表示不限制")
    parser.add_argument("--per-keyword-limit", type=int, default=0, help="每个关键词最多处理条数，0 表示不限制")
    # list 层节奏（与 qzrc_scraper / qzrc_backfill 对齐，默认 OFF）
    parser.add_argument("--batch-size", type=int, default=0,
                        help="每 N 个 (kw,pg) 项后冷却。0 = 不启用 list 节奏")
    parser.add_argument("--item-delay-min", type=float, default=2.0, help="单项间隔下限秒（list pacing 启用时）")
    parser.add_argument("--item-delay-max", type=float, default=5.0, help="单项间隔上限秒")
    parser.add_argument("--batch-delay-min", type=float, default=0.0,
                        help="批后冷却下限秒。0 = 不启用")
    parser.add_argument("--batch-delay-max", type=float, default=0.0, help="批后冷却上限秒")
    parser.add_argument("--post-captcha-multiplier", type=float, default=3.0,
                        help="命中验证码后下批冷却 × 此倍数")
    parser.add_argument("--stop-on-captcha", action="store_true",
                        help="任一批命中验证码就终止整个 run")
    # enrich 层节奏（51job 详情批量打开；沿用 qzrc enrich 命名 + 默认值）
    parser.add_argument("--enrich-batch-size", type=int, default=10,
                        help="51job 每处理多少条详情后暂停，0 表示不暂停")
    parser.add_argument("--enrich-batch-delay-min", type=float, default=180.0,
                        help="51job enrich 批次暂停最小秒数")
    parser.add_argument("--enrich-batch-delay-max", type=float, default=480.0,
                        help="51job enrich 批次暂停最大秒数")
    # 接收但忽略（与 qzrc_scraper 共享调度器命名）
    parser.add_argument("--enrich-item-delay-min", type=float, default=8.0, help=argparse.SUPPRESS)
    parser.add_argument("--enrich-item-delay-max", type=float, default=20.0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    default_keywords = TALENT_51JOB_DEFAULT_KEYWORDS if args.platform == "51job_talent" else DEFAULT_KEYWORDS
    kws = split_keywords(args.keywords, default_keywords)
    try:
        asyncio.run(scrape(
            args.platform, kws, args.max_pages, args.dry_run,
            args.captcha_timeout, args.inspect,
            delay_min=args.delay_min, delay_max=args.delay_max,
            detail_delay_min=args.detail_delay_min, detail_delay_max=args.detail_delay_max,
            max_items=args.max_items,
            per_keyword_limit=args.per_keyword_limit,
            batch_size=args.batch_size,
            item_delay_lo=args.item_delay_min, item_delay_hi=args.item_delay_max,
            batch_delay_lo=args.batch_delay_min, batch_delay_hi=args.batch_delay_max,
            stop_on_captcha=args.stop_on_captcha,
            post_captcha_multiplier=args.post_captcha_multiplier,
            enrich_batch_size=args.enrich_batch_size,
            enrich_batch_delay_lo=args.enrich_batch_delay_min,
            enrich_batch_delay_hi=args.enrich_batch_delay_max,
        ))
    except BrowserSessionError as exc:
        print(f"[BROWSER-ERROR] {exc}")
        emit_progress("failed", f"浏览器连接失败: {exc}", current=0, total=0, items_total=0)
        sys.exit(2)


if __name__ == "__main__":
    main()
