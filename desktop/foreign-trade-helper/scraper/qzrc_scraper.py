r"""
大泉州人才网爬虫 — 应聘端（职位列表）+ 招聘端（简历列表）

策略：page.route() 路由拦截所有 JSON 响应（比 page.on('response') 更可靠），
      DOM 兜底。

用法:
  & "python" scraper/qzrc_scraper.py --mode resume --inspect --max-pages 1 --keywords "跨境销售"
  & "python" scraper/qzrc_scraper.py --mode resume --max-pages 10
"""

from __future__ import annotations

import argparse
import asyncio
import json as _json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin

from platform_contract import push_all, push_talents, split_keywords

try:
    from playwright.async_api import async_playwright, Route
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
    print("[PROGRESS] " + _json.dumps(payload, ensure_ascii=False), flush=True)


# ---------------------------------------------------------------------------
USER_DATA_DIR = str(Path(__file__).parent.parent / "data" / "browser-profile")
BASE_URL = "https://www.qzrc.com"
JOB_LIST_URL = "https://www.qzrc.com/home/joblist?adv=true"
RESUME_LIST_URL = "https://www.qzrc.com/home/resumelist?adv=true"
HR_HOST = "hr.qzrc.com"

SEARCH_KEYWORDS = [
    "跨境销售", "亚马逊运营", "TikTok Shop", "跨境电商运营",
    "海外仓", "外贸销售", "独立站运营", "货代",
]

FILTER_KEYWORDS = [
    "跨境", "亚马逊", "tiktok", "海外", "外贸", "出口", "供应链",
    "海外仓", "独立站", "fba", "fbt", "shopify", "北美", "美区",
    "temu", "shein", "货代", "一件代发", "跨境电商",
]

EXCLUDE_COMPANY_KEYWORDS = [
    "人才网", "招聘网", "招聘平台", "人力资源", "劳务派遣", "猎头",
    "职业培训", "培训学校", "设计培训", "认证定点", "求职", "简历",
    # 贵司自有/关联公司：自家公司不采集（来源：用户明确要求“后续不要爬取自家公司数据”）
    "蓝蜻蜓", "福建蓝蜻蜓护理用品",
]

# 不需要拦截的静态资源，直接放行以节省时间
_SKIP_RESOURCE_TYPES = {"image", "stylesheet", "font", "media", "ping", "other"}
# ---------------------------------------------------------------------------


async def rnd_delay(lo: float = 1.2, hi: float = 3.5):
    await asyncio.sleep(random.uniform(lo, hi))


def clean(s) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s).strip())


def has_crossborder(texts: list[str]) -> bool:
    joined = " ".join(texts).lower()
    return any(kw.lower() in joined for kw in FILTER_KEYWORDS)


def is_excluded_company(company: str, texts: list[str] | None = None) -> bool:
    joined = " ".join([company, *(texts or [])]).lower()
    return any(kw.lower() in joined for kw in EXCLUDE_COMPANY_KEYWORDS)


def profile_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, out_key in [
        ("姓名", "name_masked"),
        ("学历", "education"),
        ("专业", "major"),
        ("年龄", "age"),
    ]:
        m = re.search(rf"{key}[：:]\s*([^|\n]+)", text)
        if m:
            fields[out_key] = clean(m.group(1))
    return fields


def has_talent_potential(texts: list[str], experience: str = "") -> bool:
    """目标是构建跨境人才池：只要任一文本命中跨境关键词就入库。
    资深度（主管/经理/年限）由后端 score_talent() 评分体现，不在爬虫层硬过滤。
    """
    return has_crossborder([" ".join([*texts, experience])])


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


def abs_url(url: str) -> str:
    return urljoin(BASE_URL, url) if url else ""


def pick_download_url(urls: list[str]) -> str:
    for url in urls:
        low = url.lower()
        if any(token in low for token in ("download", "down", "export", "pdf", "doc")):
            return abs_url(url)
    return ""


def pick_resume_detail_url(urls: list[str], person_id: str = "") -> str:
    for url in urls:
        if "/resume/show/" in url:
            return abs_url(url)
    return f"{BASE_URL}/resume/show/{person_id}" if person_id else RESUME_LIST_URL


# ---------------------------------------------------------------------------
# 路由拦截：捕获所有 JSON 响应
# ---------------------------------------------------------------------------

class ApiCapture:
    def __init__(self):
        self.data: list[dict] = []

    def clear(self):
        self.data.clear()

    async def make_handler(self):
        capture = self

        async def handler(route: Route):
            req = route.request
            # 只拦截 XHR / Fetch（数据接口），其余全部放行
            # document/navigation 放行 → 登录页、页面跳转不受影响
            if req.resource_type not in ("xhr", "fetch"):
                await route.continue_()
                return
            try:
                response = await route.fetch()
                ct = (response.headers.get("content-type") or "").lower()
                if "json" in ct:
                    body_bytes = await response.body()
                    try:
                        parsed = _json.loads(body_bytes.decode("utf-8", errors="ignore"))
                        capture.data.append({"url": req.url, "body": parsed})
                    except Exception:
                        pass
                await route.fulfill(response=response)
            except Exception:
                await route.continue_()

        return handler


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------

def _find_list(obj, depth=0) -> list:
    if depth > 6:
        return []
    if isinstance(obj, list) and len(obj) > 2 and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        best = []
        for v in obj.values():
            cand = _find_list(v, depth + 1)
            if len(cand) > len(best):
                best = cand
        return best
    return []


def _iter_lists(obj, depth=0):
    if depth > 8:
        return
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            yield obj
        for v in obj[:50]:
            yield from _iter_lists(v, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_lists(v, depth + 1)


def _item_score(item: dict, mode: str) -> int:
    keys = {str(k).lower() for k in item.keys()}
    if mode == "job":
        groups = [
            ("companyname", "company_name", "qymc", "unitname", "企业名称", "单位名称"),
            ("positionname", "jobname", "gwmc", "title", "职位名称", "岗位名称"),
            ("workcity", "workplace", "city", "工作地点"),
        ]
    else:
        groups = [
            ("expectposition", "expect_position", "intentionjob", "jobintention", "qzyx", "求职意向", "意向职位"),
            ("name", "username", "realname", "truename", "姓名"),
            ("expectcity", "expect_city", "workcity", "city", "意向城市", "意向地区"),
        ]
    return sum(1 for group in groups if any(k.lower() in keys for k in group))


def _candidate_lists(obj, mode: str) -> list[list[dict]]:
    scored = []
    for items in _iter_lists(obj):
        score = max((_item_score(item, mode) for item in items[:5]), default=0)
        if score:
            scored.append((score, len(items), items))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [items for _, _, items in scored]


def _get(d: dict, *keys: str) -> str:
    kl = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in kl:
            return clean(kl[k.lower()])
    return ""


def parse_job_entries(items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        company = _get(item, "companyName", "company_name", "企业名称", "单位名称", "qymc", "unitName")
        jd_title = _get(item, "positionName", "position_name", "岗位名称", "职位名称", "gwmc", "title", "jobName")
        city = _get(item, "workCity", "work_city", "工作地点", "workPlace", "city", "workArea", "workAreaName")
        salary = _get(item, "salary", "salaryRange", "薪资", "待遇", "salaryDesc")
        company_id = _get(item, "companyId", "company_id", "qyid", "unitId", "id", "eCompanyId", "ECompanyID")
        job_id = _get(item, "jobId", "job_id", "eJobId", "EJobID")
        industry = _get(item, "industry", "industryName", "行业", "hymc")
        size = _get(item, "companySize", "company_size", "规模", "staffSize")
        detail_url = _get(item, "detailUrl", "detail_url", "url", "href", "jobUrl")
        jd_description = _get(item, "require", "Require", "description", "Description", "岗位职责", "职位描述")
        company_description = _get(item, "companyDescription", "company_description", "公司简介",
                                   "qyjj", "introduction", "introduce", "intro", "companyIntro")
        company_address = _get(item, "address", "companyAddress", "company_address", "公司地址",
                               "工作地址", "workAddress", "qydz")
        contact = extract_contacts(jd_description)

        if not company or is_excluded_company(company, [jd_title, industry, jd_description]):
            continue
        if not has_crossborder([company, jd_title, industry, jd_description]):
            continue

        source_url = ""
        if detail_url:
            source_url = urljoin(BASE_URL, detail_url)
        elif company_id:
            source_url = f"{BASE_URL}/company/show/{company_id}"
        else:
            source_url = JOB_LIST_URL

        entry = {
            "platform": "qzrc", "platform_company_id": company_id,
            "company_name": company, "jd_title": jd_title, "city": city,
            "salary_range": salary, "industry": industry, "size_range": size,
            "company_address": company_address,
            "company_description": company_description[:2000] if company_description else None,
            "source_url": source_url,
            "source_mode": "job_seeker",
            "jd_description": jd_description[:2000],
            "raw_data": {"job_id": job_id, **item},
        }
        entry.update(contact)
        results.append(entry)
    return results


def parse_resume_entries(items: list[dict]) -> list[dict]:
    results = []
    for item in items:
        jd_title = _get(item, "expectPosition", "expect_position", "意向职位", "求职意向",
                        "positionName", "岗位意向", "intentionJob", "jobIntention", "qzyx",
                        "title", "currentPosition", "jobTitle", "matchingJob")
        city = _get(item, "expectCity", "expect_city", "意向城市", "意向地区", "workCity",
                    "所在城市", "liveCity", "city", "areaName", "workArea")
        name = _get(item, "name", "姓名", "userName", "realName", "trueName")
        person_id = _get(item, "resumeId", "resume_id", "id", "userId", "memberId")
        industry = _get(item, "industry", "行业", "expectIndustry", "industryName")
        experience = _get(item, "experience", "workYear", "workYearName", "工作经验", "经验")
        education = _get(item, "education", "educationName", "学历")
        major = _get(item, "major", "专业")
        salary = _get(item, "salary", "salaryExpectation", "待遇要求", "期望薪资")
        raw_summary = _get(item, "summary", "selfEvaluation", "自我评价", "description", "resumeSummary")
        detail_url = _get(item, "detailUrl", "detail_url", "resumeUrl", "url", "href")
        download_url = _get(item, "downloadUrl", "download_url", "downUrl", "fileUrl", "resumeDownloadUrl")
        source_url = abs_url(detail_url) if detail_url else pick_resume_detail_url([], person_id)

        if not has_talent_potential([jd_title, industry, raw_summary, major], experience):
            continue

        results.append({
            "platform": "qzrc",
            "platform_resume_id": person_id,
            "name_masked": name,
            "desired_title": jd_title,
            "city": city,
            "experience": experience,
            "education": education,
            "major": major,
            "salary_expectation": salary,
            "source_url": source_url,
            "resume_download_url": abs_url(download_url),
            "raw_summary": raw_summary,
            "raw_data": {
                "resume_download_url": abs_url(download_url),
                "resume_detail_url": source_url,
                **item,
            },
        })
    return results


# ---------------------------------------------------------------------------
# 公司详情页 enrich —— 抓取公司简介 + 公司地址
# ---------------------------------------------------------------------------

# 在一次 scrape session 内缓存已访问的公司详情，避免重复访问
_company_detail_cache: dict[str, dict[str, str]] = {}


def _entry_key(entry: dict) -> str:
    """生成单条线索去重键，公司/人才通用：平台主键 > 详情URL > 名称+职位。"""
    if not isinstance(entry, dict):
        return repr(entry)
    platform = entry.get("platform") or "qzrc"
    pid = entry.get("platform_company_id") or entry.get("platform_resume_id") or ""
    if pid:
        return f"{platform}:id:{pid}"
    url = entry.get("source_url") or ""
    if url:
        return f"{platform}:url:{url}"
    name = entry.get("company_name") or entry.get("name_masked") or ""
    title = entry.get("jd_title") or entry.get("desired_title") or ""
    return f"{platform}:nt:{name}:{title}"


# 用户实测：列表页“公司标签进入详情”的链接绝对路径（仅作最后兜底，定位首个卡片）
_QZRC_COMPANY_LINK_XPATH = "xpath=/html/body/div[9]/div[2]/div[2]/div[1]/div[1]/div[2]/div[1]/a"


def _qzrc_company_detail_id(url: str) -> str:
    """从 company/show/<id> 链接里取 id 片段，用于在列表页定位该公司的链接。"""
    m = re.search(r"/company/show/([A-Za-z0-9]+)", url or "")
    return m.group(1) if m else ""


async def _open_qzrc_company_detail_by_click(list_page, entry: dict, *, capture=None,
                                             timeout_ms: int = 15_000):
    """在公司列表页点击该公司的“公司标签”链接，于新标签页打开详情页（对齐 51job / 智联）。

    模拟真人从列表点进详情，规避直接 goto 详情 URL 触发的 qzrc 验证码 / 风控。
    定位优先级：href 含 /company/show/<id>（最稳）→ 公司名文本 → 用户实测的绝对 XPath（兜底）。
    点击前强制把锚点 target 置为 _blank + expect_popup，确保只开新标签页、绝不把列表页导航走。
    成功返回 (detail_page, "")；失败返回 (None, reason)，调用方据此跳过该条（不回退 goto）。
    """
    cid = entry.get("platform_company_id") or ""
    detail_id = cid or _qzrc_company_detail_id(entry.get("source_url") or "")
    company = (entry.get("company_name") or "").strip()

    candidates = []
    if detail_id:
        candidates.append(list_page.locator(f"a[href*='/company/show/{detail_id}']").first)
        candidates.append(list_page.locator(f"a[href*='{detail_id}']").first)
    if company:
        safe = company.replace("\\", "").replace('"', "")
        candidates.append(list_page.locator(f'a:has-text("{safe}")').first)
    candidates.append(list_page.locator(_QZRC_COMPANY_LINK_XPATH).first)

    anchor = None
    for cand in candidates:
        try:
            if await cand.count() > 0 and await cand.is_visible(timeout=500):
                anchor = cand
                break
        except Exception:
            continue
    if anchor is None:
        return None, "anchor_not_found"

    try:
        await anchor.scroll_into_view_if_needed()
        # 强制新标签页打开（无论原链接是否 target=_blank），杜绝同页跳转把列表页导航走
        await anchor.evaluate(
            "el => { el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener'); }"
        )
        await anchor.hover()
        await asyncio.sleep(random.uniform(0.2, 0.6))
        async with list_page.expect_popup(timeout=timeout_ms) as pop:
            await anchor.click(timeout=5000)
        detail_page = await pop.value
    except Exception:
        return None, "new_tab_timeout"

    # 详情页是新标签页，列表页的 route handler 不覆盖它 —— 给它也挂上 capture，JSON 兜底才有数据
    if capture is not None:
        try:
            await detail_page.route("**/*", await capture.make_handler())
        except Exception:
            pass
    try:
        await detail_page.wait_for_load_state("domcontentloaded", timeout=20_000)
    except Exception:
        pass
    return detail_page, ""


async def enrich_qzrc_company(page, entry: dict, *, capture=None,
                              click_from_list: bool = False) -> dict:
    """
    对单条公司线索补全 company_description + company_address。

    click_from_list=True（侧边栏采集主路径）：在“当前列表页”点击该公司链接、于新标签页打开
        详情后提取，提取完关闭新标签页、列表页保持不动 —— 与 51job / 智联完全一致的点击式。
        未能点击进入详情时直接跳过（保留列表已采集字段），不回退到 goto。
    click_from_list=False（qzrc_backfill.py 批量回填脚本）：沿用直接 page.goto 详情页的旧逻辑。
    capture: 可选的 ApiCapture 对象 —— 详情页产生的接口数据也尝试解析。
    """
    cid = entry.get("platform_company_id") or ""
    url = entry.get("source_url") or ""
    if not url and cid:
        url = f"{BASE_URL}/company/show/{cid}"
    if not url:
        return entry

    cache_key = cid or url
    if cache_key in _company_detail_cache:
        entry.update(_company_detail_cache[cache_key])
        return entry

    detail = None            # 实际用于提取的页面对象
    opened_new_tab = False   # detail 是否为需要在结束时关闭的新标签页
    try:
        if capture is not None:
            capture.clear()
        if click_from_list:
            detail, reason = await _open_qzrc_company_detail_by_click(page, entry, capture=capture)
            if detail is None:
                # 点击式：未能从列表进入详情 → 跳过补全（保留列表已采集字段），不回退 goto
                print(f"[ENRICH-CLICK] {entry.get('company_name', '?')[:30]} 未能点击进入详情（{reason}），跳过补全")
                return entry
            opened_new_tab = True
        else:
            await page.goto(url, timeout=25_000, wait_until="domcontentloaded")
            detail = page
        await rnd_delay(1.5, 2.5)
    except Exception as exc:
        print(f"[ENRICH] 打开 {url} 失败: {exc}")
        if opened_new_tab and detail is not None:
            try:
                await detail.close()
            except Exception:
                pass
        return entry

    # ─── ⓪ 验证码页检测：命中时不缓存、不写空字段、明确报错 ───
    try:
        head_text = await detail.evaluate(
            "() => (document.body && document.body.innerText || '').slice(0, 800)"
        )
    except Exception:
        head_text = ""
    _QZRC_CAPTCHA_TOKENS = (
        "本次访问需要做以下验证码校验", "拖动图片验证", "图形验证",
        "滑动验证", "请完成验证", "验证码校验",
    )
    if head_text and any(t in head_text for t in _QZRC_CAPTCHA_TOKENS):
        print(f"[CAPTCHA] qzrc 详情页命中验证码 ({url[:80]})，跳过该条且不缓存结果")
        entry["_qzrc_captcha"] = True
        if opened_new_tab:
            # 不自动绕过验证码：保留验证页并带到前台，交由人工处理
            try:
                await detail.bring_to_front()
            except Exception:
                pass
        return entry

    extras: dict[str, str] = {}

    # ─── ① 优先 DOM 区块抽取：.company-box .bk.prewrap 含完整地址 + 简介 ───
    # 实测页面结构：[地址] + "地图数据 地图 卫星" + [真正公司简介]
    try:
        prewrap_text = await detail.evaluate("""
            () => {
                const el = document.querySelector('.company-box .bk.prewrap')
                          || document.querySelector('.company-box .prewrap')
                          || document.querySelector('.bk.prewrap');
                return el ? el.innerText : '';
            }
        """)
    except Exception:
        prewrap_text = ""
    prewrap_text = clean(prewrap_text) if isinstance(prewrap_text, str) else ""

    if prewrap_text:
        # 切分点：地图数据 / 地图 卫星
        m_split = re.search(r"(地图数据|地图\s*卫星)", prewrap_text)
        if m_split:
            head = prewrap_text[:m_split.start()].strip()
            tail = prewrap_text[m_split.end():].strip()
            # head = 地址段；tail = 含地图版权前缀的简介段
            # 关键：Python re 的 \w 默认含中文，不能用 \w 写"英文/数字版权"前缀；
            # 改成精确移除已知噪声 pattern
            _MAP_NOISE_PATTERNS = [
                r"©\s*\d{2,4}(?:\s*[-/]\s*\d+)?",     # ©2024 / ©2024-2025
                r"GS\s*\(\d{2,4}\)\s*\d+\s*号?",       # GS(2023)1456号
                r"GS\s*-\s*\d+",                        # GS-1234
                r"\d{1,3}\s*°[\d'′″\s.]*",              # 经纬度
                r"地图|卫星|路线|导航|缩放|放大|缩小|交通",
                r"Tencent|腾讯|百度|高德|Google|Maps",
            ]
            tail_clean = tail
            for pat in _MAP_NOISE_PATTERNS:
                tail_clean = re.sub(pat, " ", tail_clean)
            # 折叠多空格 + 剥前置标点/号字
            tail_clean = re.sub(r"\s+", " ", tail_clean).strip()
            tail_clean = re.sub(r"^[\s©®&、，,；;。.·\-◆号]+", "", tail_clean).strip()
            tail_clean = re.sub(r"^(公司简介|公司介绍|企业简介|单位简介)[\s:：]*", "", tail_clean).strip()

            if head:
                head_clean = re.sub(r"^(公司地址|工作地址|联系地址)[\s:：]*", "", head).strip()
                head_clean = head_clean.rstrip(" ·-◆、，,；;。.").strip()
                if 4 <= len(head_clean) <= 200:
                    extras["company_address"] = head_clean[:300]
            if tail_clean and len(tail_clean) >= 20:
                extras["company_description"] = tail_clean[:2000]
            print(f"[ENRICH-DOM] prewrap 切分成功: addr={len(extras.get('company_address') or ''):d}字 / desc={len(extras.get('company_description') or ''):d}字")
        else:
            # prewrap 存在但没有"地图数据"分隔 —— 整段可能就是简介或地址
            # 用"地址样"判定来决定归属
            text = prewrap_text.strip()
            if text:
                # 用反污染逻辑判定
                _BUSINESS_HINTS_TMP = ("我们", "主营", "经营", "成立", "专注", "致力", "从事",
                                       "旗下", "始建", "创建", "是一家", "提供", "服务于")
                _addr_chars_tmp = re.compile(r"[路街号楼区省市镇村栋座层室厂园)）]")
                if any(h in text for h in _BUSINESS_HINTS_TMP) and len(text) >= 30:
                    extras["company_description"] = re.sub(r"^(公司简介|公司介绍|企业简介|单位简介)[\s:：]*", "", text).strip()[:2000]
                elif len(text) <= 200 and len(_addr_chars_tmp.findall(text)) >= 2:
                    extras["company_address"] = re.sub(r"^(公司地址|工作地址|联系地址)[\s:：]*", "", text).strip()[:300]

    # ─── ② 抓包 JSON 兜底（仅在 DOM 没拿到时）───
    if capture is not None and (not extras.get("company_description") or not extras.get("company_address")):
        for cap in capture.data:
            body = cap.get("body") or {}
            if not isinstance(body, dict):
                continue
            for k in ("companyDescription", "description", "introduction", "intro",
                      "公司简介", "qyjj", "companyIntro"):
                if isinstance(body.get(k), str) and len(body[k]) > 10:
                    extras["company_description"] = clean(body[k])[:2000]
                    break
            for k in ("address", "companyAddress", "公司地址", "qydz", "workAddress"):
                if isinstance(body.get(k), str) and body[k].strip():
                    extras["company_address"] = clean(body[k])[:300]
                    break
            for k in ("contactName", "contactPerson", "联系人", "lxr"):
                if isinstance(body.get(k), str) and body[k].strip():
                    extras["contact_name"] = clean(body[k])[:120]
                    break

    # ② DOM 兜底：用文本匹配 + 选择器尝试
    if not extras.get("company_description") or not extras.get("company_address"):
        try:
            body_text = await detail.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
        except Exception:
            body_text = ""
        body_text = clean(body_text) if isinstance(body_text, str) else ""

        # ── 简介/地址终止锚点（强化版：加入实测看到的噪声词）──
        _STOP_DESC = (
            "公司地址", "工作地址", "联系地址", "联系方式", "联系人", "招聘职位",
            "联系电话", "电话", "传真", "公司性质", "公司规模", "公司福利", "公司行业",
            # 实测页面尾部噪声
            "工作内容", "职位信息", "申请该职位", "申请此职位", "申请职位", "立即申请",
            "放入收藏", "收藏职位", "返回顶部", "Top",
            "公司地图", "地图数据", "地图 卫星", "查看地图", "地图导航", "地图",
        )
        _STOP_ADDR = (
            "联系方式", "联系人", "联系电话", "电话", "邮箱", "传真",
            "路线", "公交", "招聘职位", "公司简介",
            # 实测：地址后面常跟这些噪声
            "工作内容", "职位信息", "申请该职位", "申请此职位", "申请职位", "立即申请",
            "放入收藏", "收藏职位", "返回顶部", "Top", "返回",
            "地图数据", "地图 卫星", "查看地图", "地图导航", "地图",
        )
        desc_terminator = "|".join(_STOP_DESC)
        addr_terminator = "|".join(_STOP_ADDR)

        # ── 地址样：长度 ≤ 80 + 含「路/号/街/楼/区/省/市」+ 不含业务白名单词 ──
        _BUSINESS_HINTS = (
            "我们", "主营", "经营", "成立", "专注", "致力", "从事", "旗下", "始建",
            "创建", "是一家", "公司业务", "主要业务", "提供", "服务于", "始终",
            "秉承", "理念", "团队", "产品", "客户", "行业", "技术",
        )
        _ADDRESS_HINTS = re.compile(r"[路街号楼区省市镇村栋座层室号厂园)）]")

        def _looks_like_address(text: str) -> bool:
            t = text.strip()
            if len(t) < 6 or len(t) > 80:
                return False
            if any(h in t for h in _BUSINESS_HINTS):
                return False   # 含业务白名单 → 是简介
            hits = len(_ADDRESS_HINTS.findall(t))
            return hits >= 2   # 含 2+ 地址特征字符 → 像地址

        def _clean_addr_tail(addr: str) -> str:
            """地址末尾混入的页面噪声切掉。"""
            for stop in (
                "工作内容", "职位信息", "申请该职位", "申请此职位", "申请职位",
                "立即申请", "放入收藏", "收藏职位", "返回顶部", "Top", "◆",
                "地图数据", "地图 卫星", "查看地图", "地图导航",
            ):
                idx = addr.find(stop)
                if idx > 0:
                    addr = addr[:idx]
            return addr.rstrip(" ·-◆、，,；;。.").strip()

        # ── 简介：先找「公司简介」锚点 → 整页正则；再用 DOM selector 兜底但严格校验 ──
        if not extras.get("company_description"):
            m = re.search(
                rf"(?:公司简介|公司介绍|企业简介|单位简介)[\s:：]+(.{{20,2000}}?)(?={desc_terminator}|$)",
                body_text,
            )
            if m:
                candidate = m.group(1).strip()
                # 反污染：候选不能"看起来只是地址"
                if not _looks_like_address(candidate):
                    extras["company_description"] = candidate[:2000]
            if not extras.get("company_description"):
                # DOM selector 兜底：选择器更严格 + 同样过反污染
                for sel in [
                    "div.intro-box",
                    ".company-info-content",
                    ".company-description",
                    "[class*='company-intro']",
                    "[class*='companyIntro']",
                ]:
                    el = await detail.query_selector(sel)
                    if not el:
                        continue
                    txt = clean(await el.inner_text())
                    if len(txt) > 30 and not _looks_like_address(txt) and \
                       any(h in txt for h in _BUSINESS_HINTS):
                        extras["company_description"] = txt[:2000]
                        break

        # ── 地址：正则提取后清理 trail ──
        if not extras.get("company_address"):
            m = re.search(
                rf"(?:公司地址|工作地址|联系地址)[\s:：]+([^|\n]{{4,200}}?)(?={addr_terminator}|$)",
                body_text,
            )
            if m:
                cleaned = _clean_addr_tail(m.group(1).strip())
                if 4 <= len(cleaned) <= 150:
                    extras["company_address"] = cleaned[:300]

    # 只缓存"非空且至少拿到一个字段"的结果；空结果不缓存，下次还能重试
    if extras.get("company_description") or extras.get("company_address"):
        _company_detail_cache[cache_key] = extras
    entry.update(extras)
    # 点击式打开的详情是新标签页，提取完关闭它并把列表页带回前台（列表页全程未被导航）
    if opened_new_tab:
        try:
            await detail.close()
        except Exception:
            pass
        try:
            await page.bring_to_front()
        except Exception:
            pass
    return entry


# ---------------------------------------------------------------------------
# DOM 兜底
# ---------------------------------------------------------------------------

async def _dom_fallback(page, mode: str) -> list[dict]:
    """
    qzrc 简历列表的实际 DOM 结构（通过 inspect 确认）：
      每位求职者占 2 行：
        行A: cell[0]="姓名：XX|性别:|年龄:|学历:|专业:YYY"  cell[1]="自我评价：..."
        行B: cell[0]=求职意向  cell[1]=期望薪资  ...  cell[N]=城市
      => 通过检测 "姓名：" 识别行A，"自我评价" 开头的行跳过。

    职位列表列顺序（待确认）：
      [0]职位名  [1]公司名  [2]薪资  [3]工作地点  ...
    """
    results = []
    try:
        rows = await page.query_selector_all("table tr, table tbody tr")
        if not rows:
            rows = await page.query_selector_all(
                ".resume-item, .job-item, [class*='list-item'], "
                "[class*='resume'] > div, [class*='position'] > div"
            )

        for row in rows:
            try:
                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                cell_texts = [clean(await c.inner_text()) for c in cells]
                c0 = cell_texts[0]

                if mode == "resume":
                    detail_text = " ".join(cell_texts[6:])
                    prof = profile_fields(detail_text)

                    # ── 行型 A：profile summary ──────────────────────────────
                    if len(cell_texts) <= 2 and ("姓名：" in c0 or c0.startswith("姓名")):
                        name_m = re.search(r"姓名[：:]\s*([^\s|，,]+)", c0)
                        name = name_m.group(1) if name_m else ""
                        # 专业 字段作为意向职位的备选
                        spec_m = re.search(r"专业[：:]\s*([^|\n]+)", c0)
                        jd_title = spec_m.group(1).strip() if spec_m else c0[:40]
                        city_m = re.search(r"(泉州|福州|厦门|广州|深圳|上海|北京|杭州|宁波|东莞|[^\s|]{2,4}市)", c0)
                        city = city_m.group(1) if city_m else ""
                        experience = ""
                        salary = ""
                        if not has_talent_potential([jd_title, c0], experience):
                            continue

                    # ── 行型 B：自我评价补充行，跳过 ───────────────────────
                    elif c0.startswith("自我评价") or c0.startswith("工作经历"):
                        continue

                    # ── 行型 C：标准列顺序 [0]=求职意向 [1]=姓名 [4]=城市 ──
                    else:
                        # 搜索页展开详情后，tr 里会多出一个首列汇总单元格：
                        # [0]=整行汇总 [1]=求职意向 [2]=姓名 ... [5]=城市 [8]=详情。
                        # 未展开时则是 [0]=求职意向 [1]=姓名 ... [4]=城市。
                        shifted = (
                            len(cell_texts) >= 8
                            and cell_texts[1]
                            and cell_texts[2]
                            and cell_texts[1] in c0
                            and cell_texts[2] in c0
                        )
                        job_idx, name_idx, city_idx = (1, 2, 5) if shifted else (0, 1, 4)
                        exp_idx, salary_idx = (3, 4) if shifted else (2, 3)
                        jd_title = cell_texts[job_idx] if len(cell_texts) > job_idx else ""
                        name     = cell_texts[name_idx] if len(cell_texts) > name_idx else ""
                        city     = cell_texts[city_idx] if len(cell_texts) > city_idx else ""
                        experience = cell_texts[exp_idx] if len(cell_texts) > exp_idx else ""
                        salary = cell_texts[salary_idx] if len(cell_texts) > salary_idx else ""
                        if not has_talent_potential([jd_title, detail_text], experience):
                            continue

                else:
                    # 职位列表：[0]=职位 [1]=公司 [2或3]=城市
                    jd_title = c0
                    company  = cell_texts[1] if len(cell_texts) > 1 else ""
                    city     = cell_texts[3] if len(cell_texts) > 3 else ""
                    if not company or is_excluded_company(company, [jd_title]):
                        continue
                    if not has_crossborder([company, jd_title]):
                        continue

                row_id = await row.get_attribute("data-id") or ""
                links = await row.query_selector_all("a[href]")
                link_urls = [await a.get_attribute("href") or "" for a in links]
                link_texts = [clean(await a.inner_text()) for a in links]
                detail_url = pick_resume_detail_url(link_urls, row_id) if mode == "resume" else page.url
                download_url = ""
                if mode == "resume":
                    download_candidates = [
                        url for url, text in zip(link_urls, link_texts)
                        if "下载" in text or "download" in url.lower() or "down" in url.lower()
                    ]
                    download_url = pick_download_url(download_candidates or link_urls)
                    if not row_id:
                        m = re.search(r"/resume/show/([A-Za-z0-9]+)", detail_url)
                        row_id = m.group(1) if m else row_id
                if mode == "resume":
                    results.append({
                        "platform": "qzrc",
                        "platform_resume_id": row_id,
                        "name_masked": name,
                        "desired_title": jd_title,
                        "city": city,
                        "experience": experience,
                        "education": prof.get("education", ""),
                        "major": prof.get("major", ""),
                        "salary_expectation": salary,
                        "source_url": detail_url,
                        "resume_download_url": download_url,
                        "raw_summary": detail_text,
                        "raw_data": {
                            "resume_download_url": download_url,
                            "resume_detail_url": detail_url,
                            "profile": prof,
                        },
                    })
                else:
                    results.append({
                        "platform": "qzrc", "platform_company_id": row_id,
                        "company_name": company, "jd_title": jd_title, "city": city,
                        "source_url": detail_url,
                        "source_mode": "job_seeker",
                        "raw_data": {},
                    })
            except Exception:
                continue

    except Exception as e:
        print(f"[WARN] DOM 兜底失败: {e}")

    seen: set[str] = set()
    return [r for r in results
            if (k := f"{r.get('company_name') or r.get('name_masked')}:{r.get('jd_title') or r.get('desired_title')}") not in seen
            and not seen.add(k)]  # type: ignore


# ---------------------------------------------------------------------------
# 登录检测
# ---------------------------------------------------------------------------

async def _looks_like_login_state(page) -> tuple[bool, str]:
    """返回 (是否处于未登录态, 诊断原因)。"""
    try:
        url = page.url or ""
    except Exception:
        url = ""
    # URL 含 login / signin 通常意味着被重定向到登录页
    if any(k in url.lower() for k in ("/login", "signin", "passport")):
        return True, f"URL 命中 login 关键字: {url}"
    # 页面文本含登录按钮 / "请先登录"
    try:
        body_text = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 2000) : ''")
    except Exception:
        body_text = ""
    body_text = body_text or ""
    if any(k in body_text for k in ("请先登录", "登录后查看", "尚未登录", "请登录")):
        return True, "页面提示「请先登录」类文本"
    # 列表页空但有「登录」按钮 → 通常是 modal 未关
    if "登录" in body_text[:300] and ("简历" not in body_text and "职位" not in body_text):
        return True, "首屏只显示登录入口，未见列表内容"
    return False, ""


async def ensure_logged_in(page, target_url: str, *, prompt: bool = True, login_timeout: int = 600,
                           login_optional: bool = False) -> None:
    """导航到目标页，由用户确认登录状态后按 Enter 继续。
    --no-prompt 模式 (prompt=False)：若检测到未登录态，立即抛错而不是静默继续。
    login_optional=True（公司客户口径）：未登录也不阻塞，仅记录 [LOGIN-OPTIONAL] 后继续采集公开信息。
    """
    await page.goto(target_url, timeout=30_000, wait_until="domcontentloaded")
    await rnd_delay(1.5, 2.5)

    if login_optional:
        not_logged_in, reason = await _looks_like_login_state(page)
        if not_logged_in:
            print(f"[LOGIN-OPTIONAL] qzrc 公司客户未登录（{reason}），仅采集公开可见信息、不强制登录。")
        else:
            print("[LOGIN] qzrc 公司客户登录态检查通过，继续采集。")
        return

    if not prompt:
        not_logged_in, reason = await _looks_like_login_state(page)
        if not_logged_in:
            print(f"[LOGIN] qzrc 当前处于登录页或 session 已失效（{reason}），请在打开的浏览器里完成登录；脚本会停在当前页等待。")
            t0 = time.time()
            while time.time() - t0 < login_timeout:
                if page.is_closed():
                    raise RuntimeError("[LOGIN-FAIL] qzrc 页面已关闭，停止采集。")
                not_logged_in, reason = await _looks_like_login_state(page)
                if not not_logged_in:
                    print("[LOGIN] qzrc 登录态检查通过，继续采集。")
                    return
                await asyncio.sleep(2)
            raise RuntimeError(
                f"[LOGIN-FAIL] qzrc 登录等待超时（{login_timeout}s，最后原因：{reason}）。"
                " 请在打开的浏览器里完成登录后重新开始采集。"
            )
        print("[LOGIN] no-prompt 模式：已打开目标页面，登录态检查通过。")
        return

    print("\n[LOGIN] 浏览器已打开目标页面。")
    print("        · 如果已看到简历/职位列表内容 → 直接按 Enter 开始采集")
    print("        · 如果需要登录 → 在浏览器中登录完成后，再按 Enter\n")
    await asyncio.get_event_loop().run_in_executor(None, input, "        >>> 准备好后按 Enter <<<  ")
    await rnd_delay(1, 2)


def build_search_url(mode: str, keyword: str) -> str:
    base = "https://www.qzrc.com/home/joblist" if mode == "job" else "https://www.qzrc.com/home/resumelist"
    params = {"adv": "true"}
    if keyword:
        params["k"] = keyword
    return f"{base}?{urlencode(params)}"


async def goto_search_page(page, mode: str, keyword: str) -> None:
    url = build_search_url(mode, keyword)
    await page.goto(url, wait_until="domcontentloaded")
    await rnd_delay(2, 3)

    if HR_HOST in page.url:
        print(f"[WARN] 目标搜索页被跳转到企业后台: {page.url}")
        print("       请在打开的浏览器里点“搜索简历/职位搜索”进入列表页后再继续；")
        print("       当前截图如果是企业中心首页，说明不是解析失败，而是入口页面不对。")
        await asyncio.get_event_loop().run_in_executor(None, input, "       >>> 进入列表页后按 Enter <<<  ")
        await rnd_delay(1, 2)


# ---------------------------------------------------------------------------
# 搜索框填写
# ---------------------------------------------------------------------------

async def fill_search(page, keyword: str) -> bool:
    """尝试多种方式找到搜索框并输入关键词。"""
    selectors = [
        "input[placeholder*='请输入搜索']",   # qzrc 实际 placeholder
        "input[placeholder*='搜索的关键词']",
        "input[placeholder*='搜索']",
        "input[placeholder*='关键词']",
        "input[placeholder*='职位']",
        "input[placeholder*='求职']",
        "input[placeholder*='姓名']",
        "input.search-input", "input.keyword",
        "#keyword", "#searchKey", "#resumeKeyword",
    ]
    for sel in selectors:
        try:
            # page.fill() 不要求 is_visible，更鲁棒
            await page.fill(sel, keyword, timeout=3_000)
            await page.keyboard.press("Enter")
            await rnd_delay(2, 3)
            return True
        except Exception:
            continue
    return False


async def _scroll_to_load_more(page, rounds: int = 8, pause_lo: float = 0.8,
                               pause_hi: float = 1.6) -> bool:
    """向下滚动触发懒加载 / 下拉刷新，加载更多列表项（大泉州人才为下拉刷新出新数据）。

    返回是否检测到页面高度增长（即“可能加载了更多”）。高度连续两轮不再增长则提前停止。
    依赖驱动循环里的 _entry_key 去重 + “翻页未推进/全部重复”检测在没有新数据时停批。
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


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def _check_qzrc_captcha_on_page(page) -> bool:
    """检查列表页是否被风控验证码页拦截。"""
    try:
        head = await page.evaluate(
            "() => (document.body && document.body.innerText || '').slice(0, 800)"
        )
    except Exception:
        return False
    if not head:
        return False
    tokens = ("本次访问需要做以下验证码校验", "拖动图片验证", "图形验证",
              "滑动验证", "请完成验证", "验证码校验")
    return any(t in head for t in tokens)


async def scrape_qzrc(mode: str, keywords: list[str], max_pages: int,
                      max_items: int,
                      dry_run: bool, inspect: bool, no_prompt: bool = False,
                      enrich: bool = False,
                      login_timeout: int = 600,
                      # 列表采集节奏（默认 OFF；qzrc 列表风险较低）
                      batch_size: int = 0, item_delay_lo: float = 2.0,
                      item_delay_hi: float = 5.0,
                      batch_delay_lo: float = 0.0, batch_delay_hi: float = 0.0,
                      # enrich 节奏（默认 = 标准节奏；详情页批量打开风险高）
                      enrich_batch_size: int = 10,
                      enrich_item_delay_lo: float = 8.0,
                      enrich_item_delay_hi: float = 20.0,
                      enrich_batch_delay_lo: float = 180.0,
                      enrich_batch_delay_hi: float = 480.0,
                      stop_on_captcha: bool = False,
                      post_captcha_multiplier: float = 3.0) -> None:
    """
    两套节奏：
      列表采集：batch_size + item_delay + batch_delay  默认 OFF（qzrc 列表/API 风险低）
      详情页 enrich：enrich_* 系列                      默认标准节奏（详情页批量风险高）

    通用规则：
      - 满 batch_size → 随机 batch_delay 秒冷却（命中验证码则 × post_captcha_multiplier）
      - 不满 → 随机 item_delay 秒间隔
      - stop_on_captcha=True → 命中即终止整个 run
    """
    target_url = JOB_LIST_URL if mode == "job" else RESUME_LIST_URL
    parse_fn = parse_job_entries if mode == "job" else parse_resume_entries
    # 公司客户(job)登录可选，跨境人才(resume)登录必需
    login_policy = "optional" if mode == "job" else "required"

    pacing_enabled = batch_size > 0 and batch_delay_lo > 0
    print(f"[INFO] 大泉州人才网 mode={mode} keywords={keywords} max_pages={max_pages} max_items={max_items or 'unlimited'}")
    if pacing_enabled:
        print(f"[CFG]  采集节奏：每 {batch_size} 个 (kw,pg) 暂停 {batch_delay_lo:.0f}-{batch_delay_hi:.0f}s，"
              f"单项间隔 {item_delay_lo:.0f}-{item_delay_hi:.0f}s，"
              f"{'命中验证码即终止整批 run' if stop_on_captcha else f'命中后下批冷却 ×{post_captcha_multiplier:.1f}'}")

    total_pages = max(1, len(keywords) * max_pages)
    pages_done = 0
    platform_label = f"qzrc_{mode}"
    emit_progress(
        "start",
        f"{platform_label} 采集启动",
        current=0,
        total=total_pages,
        items_total=0,
    )

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            USER_DATA_DIR, headless=False, channel="chrome",
        )
        page = await ctx.new_page()

        # 注册路由拦截
        capture = ApiCapture()
        handler = await capture.make_handler()
        await page.route("**/*", handler)

        # 登录检查：公司客户(job)登录可选，跨境人才(resume)登录必需
        await ensure_logged_in(page, target_url, prompt=not no_prompt, login_timeout=login_timeout,
                               login_optional=(mode == "job"))

        all_entries: list[dict] = []
        seen_keys: set[str] = set()
        items_in_batch = 0       # 当前批已处理 item 数
        captcha_hit_in_batch = False
        give_up_run = False

        for kw in keywords:
            if give_up_run:
                break
            print(f"\n[KEYWORD] 搜索关键词: {kw!r}")

            kw_seen_keys: set[str] = set()
            for pg in range(1, max_pages + 1):
                if give_up_run:
                    break
                print(f"[PAGE] keyword={kw!r} page={pg}")
                emit_progress(
                    "page",
                    f"{platform_label} 第 {pg} 页",
                    current=min(pages_done + 1, total_pages),
                    total=total_pages,
                    current_keyword=kw,
                    current_page=pg,
                    items_total=len(all_entries),
                )
                capture.clear()

                if pg == 1:
                    # qzrc 支持 ?k=关键词。直接构造 URL 比找搜索框更稳，
                    # 也能避免在企业后台首页误按搜索。
                    await goto_search_page(page, mode, kw)
                    await rnd_delay(item_delay_lo, item_delay_hi)
                elif pg > 1:
                    if mode == "resume":
                        # 大泉州人才：下拉刷新出新数据（无翻页按钮）。
                        # 滚动加载后由后续去重/“全部重复”检测决定是否停批。
                        await _scroll_to_load_more(page, rounds=8)
                        await rnd_delay(item_delay_lo, item_delay_hi)
                    else:
                        jumped = False
                        for sel in [
                            f"a:text-is('{pg}')", f"li:text-is('{pg}')",
                            f"button:text-is('{pg}')",
                            "a.next, button.next, [class*='next-btn'], .el-pagination__next",
                        ]:
                            try:
                                el = await page.query_selector(sel)
                                if el and await el.is_visible():
                                    await el.click()
                                    await rnd_delay(item_delay_lo, item_delay_hi)
                                    jumped = True
                                    break
                            except Exception:
                                pass
                        if not jumped:
                            print(f"[INFO] 无法翻到第 {pg} 页，停止")
                            break

                # 等内容加载完
                await rnd_delay(2, 3)
                try:
                    await page.wait_for_function(
                        "!document.body.innerText.includes('数据加载中')",
                        timeout=10_000,
                    )
                except Exception:
                    pass
                await rnd_delay(1, 2)   # 给 route handler 时间完成异步处理

                # 列表页验证码检测 → 立即停批
                if pacing_enabled and await _check_qzrc_captcha_on_page(page):
                    print(f"[CAPTCHA] keyword={kw!r} page={pg} 命中验证码，本批停止")
                    captcha_hit_in_batch = True
                    pages_done += 1
                    emit_progress(
                        "page_done",
                        "命中验证码，已停批",
                        current=min(pages_done, total_pages),
                        total=total_pages,
                        current_keyword=kw,
                        current_page=pg,
                        items_total=len(all_entries),
                    )
                    if stop_on_captcha:
                        give_up_run = True
                    break

                # inspect 模式
                if inspect:
                    title = await page.title()
                    print(f"\n[INSPECT-PAGE] title={title!r} url={page.url}")

                    # 打印 DOM 表格前 5 行，帮助核实选择器和列顺序
                    rows_debug = await page.query_selector_all("table tr")
                    print(f"\n[INSPECT-DOM] 找到 {len(rows_debug)} 个 table tr，前 5 行单元格内容:")
                    for i, r in enumerate(rows_debug[:5]):
                        cells = await r.query_selector_all("td, th")
                        texts = [clean(await c.inner_text())[:20] for c in cells]
                        print(f"  行{i}: {texts}")

                    print(f"\n[INSPECT-API] 拦截到 {len(capture.data)} 个 JSON 响应:")
                    for cap in capture.data:  # noqa
                        body = cap["body"]
                        if isinstance(body, dict):
                            keys = list(body.keys())
                            list_field = next(
                                (k for k, v in body.items() if isinstance(v, list) and len(v) > 0), None
                            )
                            print(f"  URL : {cap['url']}")
                            print(f"  字段: {keys}")
                            if list_field:
                                sample = body[list_field][0] if body[list_field] else {}
                                print(f"  列表: {list_field!r} ({len(body[list_field])}条) 首条字段={list(sample.keys())[:12]}")
                        elif isinstance(body, list) and body:
                            print(f"  URL : {cap['url']}")
                            print(f"  数组: {len(body)} 条，首条字段={list(body[0].keys())[:12]}")
                    Path("data").mkdir(exist_ok=True)
                    shot = f"data/qzrc_inspect_{mode}_p{pg}.png"
                    await page.screenshot(path=shot, full_page=True)
                    print(f"[INSPECT] 截图: {shot}")

                # 解析 API 数据
                page_entries: list[dict] = []
                for cap in capture.data:
                    lists = _candidate_lists(cap["body"], mode)
                    if not lists:
                        items = _find_list(cap["body"])
                        lists = [items] if items else []
                    for items in lists[:3]:
                        parsed = parse_fn(items)
                        page_entries.extend(parsed)

                # DOM 兜底
                if not page_entries:
                    print("[WARN] API 无数据，DOM 兜底…")
                    page_entries = await _dom_fallback(page, mode)

                if not page_entries:
                    print(f"[INFO] 第 {pg} 页无有效数据，停止")
                    pages_done += 1
                    emit_progress(
                        "page_done",
                        "本页无有效数据",
                        current=min(pages_done, total_pages),
                        total=total_pages,
                        current_keyword=kw,
                        current_page=pg,
                        items_total=len(all_entries),
                    )
                    break

                # ── 翻页推进检测 + 去重（点击翻页若没真正切页，会拿到与前页相同的数据）──
                cur_url = page.url
                cur_keys = [_entry_key(e) for e in page_entries]
                new_for_kw = [k for k in cur_keys if k not in kw_seen_keys]
                if pg > 1 and cur_keys and not new_for_kw:
                    print(
                        f"[PAGINATION] qzrc kw={kw!r} page={pg} url={cur_url} "
                        f"本页 {len(cur_keys)} 条全部与本关键词前页重复，判定翻页未推进，停止当前关键词"
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
                for _e in page_entries:
                    _k = _entry_key(_e)
                    if _k in seen_keys:
                        dup_global += 1
                        continue
                    seen_keys.add(_k)
                    fresh_entries.append(_e)
                print(
                    f"[PAGINATION] qzrc kw={kw!r} page={pg} url={cur_url} "
                    f"本页 {len(cur_keys)} 条 / 关键词内新增 {len(new_for_kw)} / "
                    f"全局新增 {len(fresh_entries)} / 全局重复 {dup_global}"
                )
                page_entries = fresh_entries

                if max_items > 0:
                    remaining = max_items - len(all_entries)
                    if remaining <= 0:
                        give_up_run = True
                        break
                    page_entries = page_entries[:remaining]

                for entry in page_entries:
                    raw = entry.get("raw_data") if isinstance(entry.get("raw_data"), dict) else {}
                    raw.setdefault("keyword", kw)
                    raw.setdefault("search_keyword", kw)
                    raw.setdefault("page", pg)
                    entry["raw_data"] = raw
                    entry.setdefault("search_keyword", kw)
                    entry.setdefault("search_keywords", kw)
                    # 登录上下文（仅写 raw_data，不新增数据库字段）
                    raw.setdefault("login_policy", login_policy)
                    raw.setdefault("public_capture", login_policy == "optional")
                    raw.setdefault("login_wall_hit", False)

                # 大泉州公司客户：只采集列表（API JSON），不进入详情页、不回填，
                # 避免连续打开公司详情页触发 qzrc 验证码风控。
                # 如需补全简介/地址，可单独离线运行 qzrc_backfill.py，不在采集主流程里做。
                all_entries.extend(page_entries)
                print(f"[INFO] 本页 {len(page_entries)} 条，累计 {len(all_entries)} 条")
                pages_done += 1
                emit_progress(
                    "page_done",
                    f"本页 {len(page_entries)} 条，累计 {len(all_entries)} 条",
                    current=min(pages_done, total_pages),
                    total=total_pages,
                    current_keyword=kw,
                    current_page=pg,
                    items_total=len(all_entries),
                )

                if max_items > 0 and len(all_entries) >= max_items:
                    print(f"[INFO] 已达到 max_items={max_items}，提前结束")
                    give_up_run = True
                    break

                # ──── 节奏：单项间隔 + 每 batch_size 项后冷却 ────
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
                    await rnd_delay(item_delay_lo, item_delay_hi)

            # 关键词内层循环退出后（可能因 break / 完成）
            if pacing_enabled and captcha_hit_in_batch and not stop_on_captcha:
                # 跨关键词中断的情况：批次未满但已 break，按情况冷却
                cool = random.uniform(batch_delay_lo, batch_delay_hi) * post_captcha_multiplier
                print(f"[COOLDOWN] keyword 中断后冷却 {cool:.0f}s")
                await asyncio.sleep(cool)
                items_in_batch = 0
                captcha_hit_in_batch = False

        print(f"\n[INFO] 采集完成，共 {len(all_entries)} 条")
        emit_progress(
            "done",
            f"采集完成，共 {len(all_entries)} 条",
            current=total_pages,
            total=total_pages,
            items_total=len(all_entries),
            percent=100,
        )
        if mode == "resume":
            push_talents(all_entries, dry_run=dry_run)
        else:
            push_all(all_entries, dry_run=dry_run)
        await ctx.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="大泉州人才网爬虫",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--mode", choices=["job", "resume"], default="resume")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=0, help="本次最多采集条数，0 表示不限制")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect", action="store_true", help="打印 API 接口结构 + 截图")
    parser.add_argument("--no-prompt", action="store_true", help="批量任务模式：不等待手动按 Enter")
    parser.add_argument("--login-timeout", type=int, default=600, help="no-prompt 模式下遇到登录页时等待手动登录的秒数")
    parser.add_argument("--enrich", action="store_true",
                        help="job 模式下访问每条公司详情页，补全公司简介/地址（增加耗时）")
    # ─── 列表采集节奏（默认 OFF；qzrc 列表/API 风险较低）──
    parser.add_argument("--batch-size", type=int, default=0,
                        help="列表采集：每 N 个 (kw,pg) 项后冷却。0 = OFF（默认，列表风险低）")
    parser.add_argument("--item-delay-min", type=float, default=2.0, help="列表：单项间隔下限秒")
    parser.add_argument("--item-delay-max", type=float, default=5.0, help="列表：单项间隔上限秒")
    parser.add_argument("--batch-delay-min", type=float, default=0.0,
                        help="列表：批后冷却下限秒。0 = OFF")
    parser.add_argument("--batch-delay-max", type=float, default=0.0, help="列表：批后冷却上限秒")
    # ─── enrich 节奏（默认 = 标准节奏；详情页批量风险高）──
    parser.add_argument("--enrich-batch-size", type=int, default=10,
                        help="enrich：每 N 个详情页后冷却（默认 10）。0 = OFF")
    parser.add_argument("--enrich-item-delay-min", type=float, default=8.0, help="enrich：单项间隔下限秒")
    parser.add_argument("--enrich-item-delay-max", type=float, default=20.0, help="enrich：单项间隔上限秒")
    parser.add_argument("--enrich-batch-delay-min", type=float, default=180.0,
                        help="enrich：批后冷却下限秒（默认 3min）")
    parser.add_argument("--enrich-batch-delay-max", type=float, default=480.0,
                        help="enrich：批后冷却上限秒（默认 8min）")
    # ─── 通用 ──
    parser.add_argument("--post-captcha-multiplier", type=float, default=3.0,
                        help="命中验证码后下批冷却 × 此倍数（列表 + enrich 共用）")
    parser.add_argument("--stop-on-captcha", action="store_true",
                        help="任一批命中验证码就终止整个 run（列表 + enrich 共用）")
    args = parser.parse_args()

    kws = split_keywords(args.keywords, SEARCH_KEYWORDS)
    asyncio.run(scrape_qzrc(
        args.mode, kws, args.max_pages, args.max_items, args.dry_run, args.inspect,
        args.no_prompt, args.enrich,
        login_timeout=args.login_timeout,
        batch_size=args.batch_size,
        item_delay_lo=args.item_delay_min, item_delay_hi=args.item_delay_max,
        batch_delay_lo=args.batch_delay_min, batch_delay_hi=args.batch_delay_max,
        enrich_batch_size=args.enrich_batch_size,
        enrich_item_delay_lo=args.enrich_item_delay_min,
        enrich_item_delay_hi=args.enrich_item_delay_max,
        enrich_batch_delay_lo=args.enrich_batch_delay_min,
        enrich_batch_delay_hi=args.enrich_batch_delay_max,
        stop_on_captcha=args.stop_on_captcha,
        post_captcha_multiplier=args.post_captcha_multiplier,
    ))


if __name__ == "__main__":
    main()
