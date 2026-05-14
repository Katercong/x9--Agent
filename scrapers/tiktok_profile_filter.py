import asyncio
import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from playwright.async_api import Page, async_playwright

# ====================== Config ======================
KEYWORD = "你的关键词"               # Example: "美妆教程" "健身vlog" "穿搭"
MAX_PROCESS = 80                     # Start small for testing.
MIN_FOLLOWERS = 10000                # Minimum follower count.
MIN_TOTAL_LIKES = 500000             # Minimum total likes.

SAVE_FILE = "tiktok_targets.json"
USER_DATA_DIR = "tiktok-browser-profile"
BROWSER_CHANNEL = "chrome"           # Use installed Google Chrome. Set to "" to use bundled Chromium.
CONNECT_OVER_CDP_URL = "http://127.0.0.1:9222"

# Engagement extension points. These are intentionally disabled by default.
# Add your own implementation inside on_like_video/on_follow_profile if needed.
ENABLE_ENGAGEMENT_HOOKS = False
MATCHED_PROFILE_ACTIONS = ["like_video", "follow_profile"]

# ====================================================


async def random_delay(min_sec: float = 1.8, max_sec: float = 5.0) -> None:
    """Wait a random amount of time between visible browser actions."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


def parse_compact_number(value: Any) -> int:
    """Parse values like 10K, 1.2M, 3,400, 2万, and 1.5亿."""
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value or "").strip()
    if not text:
        return 0

    normalized = text.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)([KkMmBb万億亿]?)", normalized)
    if not match:
        return 0

    number = float(match.group(1))
    suffix = match.group(2).lower()
    multipliers = {
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
        "万": 10_000,
        "億": 100_000_000,
        "亿": 100_000_000,
    }
    return int(number * multipliers.get(suffix, 1))


def load_targets() -> list[dict[str, Any]]:
    path = Path(SAVE_FILE)
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
        path.rename(backup)
        print(f"Existing JSON was invalid. Backed it up to: {backup}")
        return []

    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def save_targets(targets: list[dict[str, Any]]) -> None:
    Path(SAVE_FILE).write_text(
        json.dumps(targets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def profile_key(profile: dict[str, Any]) -> str:
    return str(profile.get("profile_url") or profile.get("uniqueId") or "").lower()


def build_seen_keys(targets: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for item in targets:
        key = profile_key(item)
        if key:
            keys.add(key)
        unique_id = str(item.get("uniqueId") or "").lower()
        if unique_id:
            keys.add(unique_id)
    return keys


def extract_username_from_url(url: str) -> str:
    match = re.search(r"tiktok\.com/@([^/?#]+)", url)
    return match.group(1) if match else ""


def profile_url_from_video_url(video_url: str) -> str:
    username = extract_username_from_url(video_url)
    if not username:
        return ""
    return f"https://www.tiktok.com/@{username}"


def canonicalize_url(url: str) -> str:
    return url.split("?")[0].split("#")[0]


async def collect_video_links(page: Page) -> list[str]:
    links = await page.locator('a[href*="/video/"]').evaluate_all(
        """anchors => anchors
            .map(anchor => anchor.href)
            .filter(Boolean)
        """
    )

    seen: set[str] = set()
    result: list[str] = []
    for raw_url in links:
        url = canonicalize_url(str(raw_url))
        if "/video/" not in url or url in seen:
            continue
        seen.add(url)
        result.append(url)
    return result


async def find_author_profile_url(page: Page) -> str:
    direct_url = profile_url_from_video_url(page.url)
    if direct_url:
        return direct_url

    selectors = [
        '[data-e2e="browse-username"] a',
        '[data-e2="video-author-uniqueid"] a',
        'h3[data-e2="video-author-uniqueid"] a',
        'a[href^="/@"]',
        'a[href*="tiktok.com/@"]',
    ]

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            href = await locator.get_attribute("href", timeout=3000)
        except Exception:
            continue
        if not href:
            continue
        if href.startswith("/@"):
            return f"https://www.tiktok.com{href.split('?')[0]}"
        if "tiktok.com/@" in href:
            return canonicalize_url(href)

    return ""


def extract_profile_from_json(data: Any, current_url: str) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []

    if isinstance(data, dict):
        scope = data.get("__DEFAULT_SCOPE__", {})
        if isinstance(scope, dict):
            user_detail = scope.get("webapp.user-detail", {})
            if isinstance(user_detail, dict):
                user_info = user_detail.get("userInfo", {})
                if isinstance(user_info, dict):
                    candidates.append(user_info)

            user_module = scope.get("UserModule", {})
            if isinstance(user_module, dict):
                users = user_module.get("users", {})
                stats = user_module.get("stats", {})
                if isinstance(users, dict):
                    for user_id, user in users.items():
                        if isinstance(user, dict):
                            candidates.append({"user": user, "stats": stats.get(user_id, {}) if isinstance(stats, dict) else {}})

    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            user = item.get("user")
            stats = item.get("stats")
            if isinstance(user, dict) and isinstance(stats, dict):
                candidates.append({"user": user, "stats": stats})
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)

    for candidate in candidates:
        user_info = candidate.get("user", {}) if isinstance(candidate, dict) else {}
        stats = candidate.get("stats", {}) if isinstance(candidate, dict) else {}
        if not isinstance(user_info, dict):
            continue

        unique_id = user_info.get("uniqueId") or user_info.get("unique_id") or ""
        if not unique_id:
            continue

        return {
            "uniqueId": str(unique_id),
            "nickname": str(user_info.get("nickname") or ""),
            "bio": str(user_info.get("signature") or ""),
            "followers": parse_compact_number(stats.get("followerCount")),
            "following": parse_compact_number(stats.get("followingCount")),
            "total_likes": parse_compact_number(stats.get("heartCount") or stats.get("diggCount")),
            "video_count": parse_compact_number(stats.get("videoCount")),
            "verified": bool(user_info.get("verified")),
            "profile_url": f"https://www.tiktok.com/@{unique_id}",
        }

    username = extract_username_from_url(current_url)
    if username:
        return {
            "uniqueId": username,
            "nickname": "",
            "bio": "",
            "followers": 0,
            "following": 0,
            "total_likes": 0,
            "video_count": 0,
            "verified": False,
            "profile_url": f"https://www.tiktok.com/@{username}",
        }

    return None


async def extract_profile_info(page: Page) -> dict[str, Any]:
    """Extract public profile information, preferring TikTok embedded JSON."""
    profile: dict[str, Any] = {
        "uniqueId": "",
        "nickname": "",
        "bio": "",
        "followers": 0,
        "following": 0,
        "total_likes": 0,
        "video_count": 0,
        "verified": False,
        "profile_url": page.url,
    }

    try:
        scripts = await page.locator(
            'script#__UNIVERSAL_DATA_FOR_REHYDRATION__, script#__NEXT_DATA__, script[type="application/json"]'
        ).all()
        for script in scripts:
            json_text = await script.inner_text()
            if not json_text.strip().startswith(("{", "[")):
                continue
            data = json.loads(json_text)
            extracted = extract_profile_from_json(data, page.url)
            if extracted and extracted.get("uniqueId"):
                profile.update(extracted)
                return profile
    except Exception as exc:
        print(f"JSON extraction failed: {exc}")

    try:
        raw = await page.evaluate(
            """() => {
                const textFrom = (selectors) => {
                    for (const selector of selectors) {
                        const element = document.querySelector(selector);
                        const text = element && element.innerText && element.innerText.trim();
                        if (text) return text;
                    }
                    return "";
                };
                return {
                    currentUrl: window.location.href,
                    visibleText: document.body ? document.body.innerText : "",
                    username: textFrom(['[data-e2e="user-title"]', '[data-e2="browser-username"]', 'h1']),
                    nickname: textFrom(['[data-e2e="user-subtitle"]', 'h2']),
                    bio: textFrom(['[data-e2e="user-bio"]', '[data-e2="user-bio"]']),
                    followersRaw: textFrom(['[data-e2e="followers-count"]']),
                    followingRaw: textFrom(['[data-e2e="following-count"]']),
                    likesRaw: textFrom(['[data-e2e="likes-count"]']),
                    strongTexts: Array.from(document.querySelectorAll('strong[data-e2e]'))
                        .map((element) => element.innerText || element.textContent || "")
                };
            }"""
        )

        username = str(raw.get("username") or "").lstrip("@").strip()
        if not username:
            username = extract_username_from_url(str(raw.get("currentUrl") or page.url))

        strong_texts = [str(value).strip() for value in raw.get("strongTexts", []) if str(value).strip()]
        following = parse_compact_number(raw.get("followingRaw"))
        followers = parse_compact_number(raw.get("followersRaw"))
        likes = parse_compact_number(raw.get("likesRaw"))

        if len(strong_texts) >= 3:
            following = following or parse_compact_number(strong_texts[0])
            followers = followers or parse_compact_number(strong_texts[1])
            likes = likes or parse_compact_number(strong_texts[2])

        profile.update(
            {
                "uniqueId": username,
                "nickname": str(raw.get("nickname") or username),
                "bio": str(raw.get("bio") or ""),
                "followers": followers,
                "following": following,
                "total_likes": likes,
                "video_count": await page.locator('a[href*="/video/"]').count(),
                "verified": "verified" in str(raw.get("visibleText") or "").lower(),
                "profile_url": f"https://www.tiktok.com/@{username}" if username else page.url,
            }
        )
    except Exception as exc:
        print(f"HTML fallback extraction failed: {exc}")

    return profile


def is_target(profile: dict[str, Any]) -> bool:
    """Edit this function to change filtering logic."""
    if profile.get("followers", 0) < MIN_FOLLOWERS:
        return False
    if profile.get("total_likes", 0) < MIN_TOTAL_LIKES:
        return False

    bio_lower = str(profile.get("bio", "")).lower()
    if any(word in bio_lower for word in ["合作", "商务", "品牌", "collaboration", "business"]):
        return True

    return True


async def handle_matched_profile(
    page: Page,
    profile: dict[str, Any],
    video_url: str,
    profile_url: str,
) -> dict[str, Any]:
    """Single interface called after a profile matches the filter."""
    profile["review_status"] = "pending_manual_review"
    profile["requested_actions"] = MATCHED_PROFILE_ACTIONS.copy()
    profile["engagement_result"] = await run_engagement_hooks(
        page=page,
        profile=profile,
        video_url=video_url,
        profile_url=profile_url,
    )
    return profile


async def run_engagement_hooks(
    page: Page,
    profile: dict[str, Any],
    video_url: str,
    profile_url: str,
) -> dict[str, str]:
    """Dispatch optional matched-profile actions through one stable interface."""
    result = {
        "like_video": "disabled",
        "follow_profile": "disabled",
    }

    if not ENABLE_ENGAGEMENT_HOOKS:
        return result

    if "like_video" in MATCHED_PROFILE_ACTIONS:
        result["like_video"] = await on_like_video(page, video_url, profile)

    if "follow_profile" in MATCHED_PROFILE_ACTIONS:
        result["follow_profile"] = await on_follow_profile(page, profile_url, profile)

    return result


async def on_like_video(page: Page, video_url: str, profile: dict[str, Any]) -> str:
    """Hook for a user-supplied video-like implementation."""
    _ = page, video_url, profile
    return "not_implemented"


async def on_follow_profile(page: Page, profile_url: str, profile: dict[str, Any]) -> str:
    """Hook for a user-supplied profile-follow implementation."""
    _ = page, profile_url, profile
    return "not_implemented"


async def pause_for_manual_gate_if_needed(page: Page) -> None:
    try:
        text = (await page.locator("body").inner_text(timeout=3000)).lower()
    except Exception:
        return

    gate_words = ["captcha", "verify", "verification", "login", "log in", "sign up", "验证码", "验证", "登录"]
    if any(word in text for word in gate_words):
        print("TikTok may be showing login or verification. Handle it in the browser.")
        input("After manual handling, press Enter to continue...")


async def get_page_from_daily_chrome(playwright: Any) -> tuple[Any, Page, bool]:
    """Connect to a Chrome instance started with --remote-debugging-port=9222."""
    try:
        browser = await playwright.chromium.connect_over_cdp(CONNECT_OVER_CDP_URL)
    except Exception as exc:
        raise RuntimeError(
            "Could not connect to your daily Chrome session.\n"
            "Close all Chrome windows, then start Chrome with this PowerShell command:\n\n"
            'Start-Process "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe" '
            '-ArgumentList "--remote-debugging-port=9222", "--profile-directory=Default"\n\n'
            "After Chrome opens and you confirm TikTok is logged in, run this script again."
        ) from exc

    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = await context.new_page()
    return browser, page, True


async def get_page_from_managed_chrome(playwright: Any) -> tuple[Any, Page, bool]:
    """Launch a script-managed browser profile."""
    context = await playwright.chromium.launch_persistent_context(
        USER_DATA_DIR,
        channel=BROWSER_CHANNEL or None,
        headless=False,
        slow_mo=300,
        viewport={"width": 1280, "height": 960},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
    )
    page: Page = context.pages[0] if context.pages else await context.new_page()
    return context, page, False


async def main() -> None:
    async with async_playwright() as p:
        if CONNECT_OVER_CDP_URL:
            browser_or_context, page, connected_daily_chrome = await get_page_from_daily_chrome(p)
            print(f"Connected to daily Chrome session: {CONNECT_OVER_CDP_URL}")
        else:
            browser_or_context, page, connected_daily_chrome = await get_page_from_managed_chrome(p)

        print("Please log in to TikTok manually in the opened browser if needed.")
        await page.goto("https://www.tiktok.com/", wait_until="domcontentloaded")
        input("After login is ready, press Enter to continue...")

        search_url = f"https://www.tiktok.com/search/video?q={quote_plus(KEYWORD)}"
        await page.goto(search_url, wait_until="domcontentloaded")
        await random_delay(4, 6)
        await pause_for_manual_gate_if_needed(page)
        print(f"Search page opened: {KEYWORD}")

        targets = load_targets()
        seen_keys = build_seen_keys(targets)
        video_links: list[str] = []
        processed = 0

        while processed < MAX_PROCESS:
            print(f"\n=== Processing video {processed + 1} ===")

            try:
                while processed >= len(video_links):
                    new_links = await collect_video_links(page)
                    for link in new_links:
                        if link not in video_links:
                            video_links.append(link)

                    if processed < len(video_links):
                        break

                    await page.mouse.wheel(0, 1200)
                    await random_delay(3, 5)

                    if not new_links:
                        print("No more visible video links found.")
                        processed = MAX_PROCESS
                        break

                if processed >= MAX_PROCESS or processed >= len(video_links):
                    break

                video_url = video_links[processed]
                await page.goto(video_url, wait_until="domcontentloaded")
                await random_delay(4, 7)
                await pause_for_manual_gate_if_needed(page)

                profile_url = await find_author_profile_url(page)
                if not profile_url:
                    print("Could not find author profile URL. Skipping.")
                    processed += 1
                    await page.goto(search_url, wait_until="domcontentloaded")
                    continue

                await page.goto(profile_url, wait_until="domcontentloaded")
                await random_delay(3.5, 6)
                await pause_for_manual_gate_if_needed(page)

                profile = await extract_profile_info(page)
                profile["source_video_url"] = video_url
                profile["source_keyword"] = KEYWORD
                profile["matched_at"] = datetime.now().isoformat(timespec="seconds")
                profile["review_status"] = "pending_manual_review"

                if profile and profile.get("uniqueId"):
                    print(
                        f"Checking @{profile['uniqueId']} | "
                        f"followers: {profile['followers']} | "
                        f"likes: {profile['total_likes']}"
                    )

                    current_keys = {profile_key(profile), str(profile.get("uniqueId") or "").lower()}
                    if any(key and key in seen_keys for key in current_keys):
                        print("Already saved before. Skipping duplicate.")
                    elif is_target(profile):
                        profile = await handle_matched_profile(page, profile, video_url, profile_url)
                        print("Matched. Saved to manual review queue.")
                        targets.append(profile)
                        for key in current_keys:
                            if key:
                                seen_keys.add(key)
                        save_targets(targets)
                    else:
                        print("Not matched. Skipping.")
                else:
                    print("Could not extract user info. Skipping.")

                await page.goto(search_url, wait_until="domcontentloaded")
                await random_delay(2, 3)

                if processed % 6 == 0 and processed > 0:
                    await page.mouse.wheel(0, 1200)
                    await random_delay(3, 5)

            except Exception as exc:
                print(f"Error while processing current video: {exc}")
                try:
                    await page.goto(search_url, wait_until="domcontentloaded")
                    await random_delay(2, 3)
                except Exception:
                    pass

            processed += 1

        print(f"\nDone. Processed {processed} videos, found {len(targets)} matching accounts.")
        print(f"Results saved to: {SAVE_FILE}")
        if not connected_daily_chrome:
            await browser_or_context.close()


if __name__ == "__main__":
    asyncio.run(main())
