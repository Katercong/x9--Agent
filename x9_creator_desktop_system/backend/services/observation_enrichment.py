from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any

from ..utils.json_utils import parse_followers_count


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>'\"]+|"
    r"(?:wa\.me|api\.whatsapp\.com|chat\.whatsapp\.com|t\.me|telegram\.me|"
    r"instagram\.com|linktr\.ee|beacons\.ai|bio\.site|taplink\.cc|stan\.store|"
    r"line\.me|lin\.ee|m\.me|facebook\.com)/[^\s<>'\"]+",
    re.IGNORECASE,
)
TIKTOK_HANDLE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?tiktok\.com/@(?P<handle>[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
AT_HANDLE_RE = re.compile(r"(?<![\w.])@(?P<handle>[A-Za-z0-9][A-Za-z0-9._-]{1,80})")
FOLLOWERS_BEFORE_RE = re.compile(
    r"(?P<num>\d[\d,.]*\.?\d*)\s*(?P<suffix>[KkMmBb]|万|萬|亿|億)?\s*"
    r"(?:followers?|fans|粉丝|粉絲|关注者)",
    re.IGNORECASE,
)
FOLLOWERS_AFTER_RE = re.compile(
    r"(?:followers?|fans|粉丝|粉絲|关注者)\s*[:：]?\s*"
    r"(?P<num>\d[\d,.]*\.?\d*)\s*(?P<suffix>[KkMmBb]|万|萬|亿|億)?",
    re.IGNORECASE,
)
SHOP_VALUE_RE = re.compile(r"^\$?\d[\d,.]*(?:\.\d+)?\s*(?:[KkMmBb]|万|萬|亿|億)?%?$")
SHOP_SCORE_RE = re.compile(r"^\d+(?:\.\d+)?\s*/\s*(?:5(?:\.0)?|100)(?:\w+)?$")

HANDLE_STOPWORDS = {
    "about",
    "account",
    "accounts",
    "following",
    "followers",
    "for",
    "login",
    "shop",
    "tiktok",
    "video",
    "videos",
    "www",
}
BIO_SKIP_LINES = {
    "follow",
    "followers",
    "following",
    "likes",
    "message",
    "share",
    "tiktok",
    "upload",
}


def enrich_observation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copied observation with compact, system-ready creator fields.

    The full incoming payload is still retained in raw_observations.raw_json.
    This layer only adds normalized fields and a small enrichment summary so
    the CRM/pipeline can use data that the browser already collected.
    """
    enriched = copy.deepcopy(payload)
    creator = enriched.get("creator")
    if not isinstance(creator, dict):
        creator = {}
        enriched["creator"] = creator
    raw_profile = enriched.get("raw_profile")
    if not isinstance(raw_profile, dict):
        raw_profile = {}

    platform = (enriched.get("platform") or "tiktok").lower()
    shop = enriched.get("tiktok_shop") if isinstance(enriched.get("tiktok_shop"), dict) else {}
    texts = _collect_text_entries(enriched, creator, raw_profile, shop)
    all_text = "\n".join(value for _, value in texts if value)
    raw_handle_text = str(creator.get("handle") or "").strip()
    raw_display_name = str(creator.get("display_name") or "").strip()
    display_name_handle = _clean_handle(raw_display_name) if platform == "tiktok_shop" else ""

    handle = (
        _clean_handle(creator.get("handle"))
        or _clean_handle(creator.get("username"))
        or _clean_handle(creator.get("unique_id"))
        or _clean_handle(creator.get("uniqueId"))
        or _clean_handle(raw_profile.get("username"))
        or _clean_handle(raw_profile.get("unique_id"))
        or _clean_handle(raw_profile.get("uniqueId"))
        or _clean_handle(_shop_list_value(shop, "handle"))
        or _handle_from_urls(enriched, creator, shop)
        or _handle_from_text(all_text)
        or display_name_handle
    )
    if handle:
        creator["handle"] = handle
        if display_name_handle and handle == display_name_handle and raw_handle_text and not _clean_handle(raw_handle_text):
            creator["display_name"] = raw_handle_text
        if not creator.get("profile_url"):
            creator["profile_url"] = f"https://www.tiktok.com/@{handle}"
    else:
        creator["handle"] = ""
        if raw_handle_text and not _clean_handle(raw_handle_text) and not creator.get("display_name"):
            creator["display_name"] = raw_handle_text

    if not creator.get("display_name"):
        creator["display_name"] = (
            creator.get("nickname")
            or creator.get("name")
            or raw_profile.get("nickname")
            or raw_profile.get("display_name")
            or _shop_list_value(shop, "display_name")
            or handle
            or ""
        )

    emails = _merge_unique(
        _existing_values(creator.get("email"))
        + _existing_values(creator.get("emails"))
        + _existing_values(creator.get("emails_json"))
        + _existing_values(raw_profile.get("email"))
        + _existing_values(raw_profile.get("emails"))
        + _existing_values(raw_profile.get("emails_json"))
        + _extract_emails(all_text)
    )
    if emails:
        creator["emails"] = emails
        if not creator.get("email"):
            creator["email"] = emails[0]

    external_links = _merge_unique_links(
        _iter_link_values(creator.get("external_links"))
        + _iter_link_values(creator.get("website"))
        + _iter_link_values(creator.get("link"))
        + _iter_link_values(raw_profile.get("external_links"))
        + _iter_link_values(raw_profile.get("website"))
        + _iter_link_values(raw_profile.get("link"))
        + _iter_shop_links(shop)
        + _extract_links(all_text)
    )
    if external_links:
        creator["external_links"] = external_links

    if not creator.get("followers_raw"):
        raw_followers = raw_profile.get("followers_raw")
        if raw_followers:
            creator["followers_raw"] = raw_followers
    if not creator.get("followers_raw"):
        raw_followers = _extract_followers_raw(all_text)
        if raw_followers:
            creator["followers_raw"] = raw_followers
    shop_detail = extract_shop_detail_fields(all_text) if platform == "tiktok_shop" else {}
    detail_followers = shop_detail.get("followers_raw")
    if detail_followers and _should_replace_followers(creator.get("followers_raw"), detail_followers):
        creator["followers_raw"] = detail_followers
    coerced_count = _coerce_int(creator.get("followers_count"))
    if coerced_count is None:
        coerced_count = _coerce_int(raw_profile.get("followers_count"))
    detail_count = _coerce_int(detail_followers)
    if detail_count is not None and (coerced_count is None or coerced_count < 1000 <= detail_count or coerced_count < detail_count / 10):
        coerced_count = detail_count
    if coerced_count is not None:
        creator["followers_count"] = coerced_count
    else:
        parsed_followers = parse_followers_count(creator.get("followers_raw"))
        if parsed_followers is not None:
            creator["followers_count"] = parsed_followers

    if shop_detail:
        shop.setdefault("server_extracted", {}).update(shop_detail)

    if not creator.get("bio") and platform != "tiktok_shop":
        bio_excerpt = _profile_text_excerpt(texts)
        if bio_excerpt:
            creator["bio"] = bio_excerpt

    enrichment = enriched.get("enrichment") if isinstance(enriched.get("enrichment"), dict) else {}
    enrichment.update({
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "source_text_fields": [name for name, value in texts if value],
        "emails": emails,
        "external_links": external_links,
        "inferred_handle": handle or None,
        "text_excerpt": _compact_text_excerpt(texts),
        "raw_preserved_in": "raw_observations.raw_json",
    })
    enriched["enrichment"] = enrichment
    return enriched


def build_profile_snapshot(payload: dict[str, Any], creator_data: dict[str, Any]) -> dict[str, Any]:
    enrichment = payload.get("enrichment") if isinstance(payload.get("enrichment"), dict) else {}
    raw_profile = payload.get("raw_profile") if isinstance(payload.get("raw_profile"), dict) else {}
    snapshot = {
        "processed_at": enrichment.get("processed_at") or datetime.now(timezone.utc).isoformat(),
        "lead_status": payload.get("lead_status"),
        "filter_reason": payload.get("filter_reason"),
        "filter_message": payload.get("filter_message"),
        "source": payload.get("source"),
        "source_url": creator_data.get("source_url") or raw_profile.get("source_url") or payload.get("source_url") or payload.get("current_url"),
        "profile_url": creator_data.get("profile_url") or raw_profile.get("profile_url"),
        "shop_profile_url": creator_data.get("shop_profile_url") or raw_profile.get("shop_profile_url"),
        "following_raw": creator_data.get("following_raw") or raw_profile.get("following_raw"),
        "likes_raw": creator_data.get("likes_raw") or raw_profile.get("likes_raw"),
        "emails": creator_data.get("emails") or enrichment.get("emails") or [],
        "external_links": creator_data.get("external_links") or enrichment.get("external_links") or [],
        "source_text_fields": enrichment.get("source_text_fields") or [],
        "text_excerpt": enrichment.get("text_excerpt"),
    }
    return {key: value for key, value in snapshot.items() if value not in (None, "", [], {})}


def extract_shop_detail_fields(text: str) -> dict[str, str]:
    """Parse compact TikTok Shop detail metrics from visible text.

    The browser extension sends raw page text only. This keeps the extraction
    server-side and preserves the full raw text in raw_observations.
    """
    lines = _shop_lines(text)
    if not lines:
        return {}

    out: dict[str, str] = {}
    mappings = {
        "gmv_raw": ("GMV", _looks_money),
        "items_sold_raw": ("Items sold", _looks_count_value),
        "gpm_raw": ("GPM", _looks_money),
        "gmv_per_customer_raw": ("GMV per customer", _looks_money),
        "est_post_rate_raw": ("Est. post rate", _looks_percent),
        "avg_commission_rate_raw": ("Avg. commission rate", _looks_percent),
        "products_raw": ("Products", _looks_count_value),
        "brand_collaborations_raw": ("Brand collaborations", _looks_count_value),
        "video_gpm_raw": ("Video GPM", _looks_money),
        "videos_raw": ("Videos", _looks_count_value),
        "avg_video_views_raw": ("Avg. video views", _looks_count_value),
        "avg_video_engagement_rate_raw": ("Avg. video engagement rate", _looks_percent),
        "live_gpm_raw": ("LIVE GPM", _looks_money),
        "live_streams_raw": ("LIVE streams", _looks_count_value),
        "avg_live_views_raw": ("Avg. LIVE views", _looks_count_value),
        "avg_live_engagement_rate_raw": ("Avg. LIVE engagement rate", _looks_percent),
    }
    for key, (label, predicate) in mappings.items():
        value = _value_after_label(lines, label, predicate)
        if value:
            out[key] = value

    followers = _value_after_label(lines, "Followers", _looks_count_value, max_scan=4)
    if followers:
        out["followers_raw"] = followers
    category = _shop_category(lines)
    if category:
        out["category_text"] = category
    rating = _value_after_label(lines, "Rating", lambda v: not _is_shop_section(v), max_scan=3)
    if rating:
        out["rating_text"] = rating
    flat_fee = _value_after_label(lines, "Flat fee", lambda v: not _is_shop_section(v), max_scan=3)
    if flat_fee:
        out["flat_fee_text"] = flat_fee

    pps = _first_score(lines)
    if pps:
        out["pps_score_raw"] = pps
    sample = _value_after_label(lines, "Sample score", _looks_score, max_scan=6)
    if sample:
        out["sample_score_raw"] = sample
    gender = _shop_gender(lines)
    out.update(gender)
    return out


def _collect_text_entries(
    payload: dict[str, Any],
    creator: dict[str, Any],
    raw_profile: dict[str, Any],
    shop: dict[str, Any],
) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []

    def add(name: str, value: Any, limit: int = 300_000) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        entries.append((name, text[:limit]))

    for key in (
        "bio",
        "signature",
        "description",
        "visible_text",
        "raw_visible_text",
        "raw_text",
        "source_url",
        "profile_url",
        "shop_profile_url",
    ):
        add(f"creator.{key}", creator.get(key))
    for key in ("visible_text", "raw_visible_text", "raw_text", "current_url", "source_url"):
        add(key, payload.get(key))
    for key in (
        "bio",
        "signature",
        "description",
        "visible_text",
        "raw_visible_text",
        "raw_text",
        "source_url",
        "profile_url",
        "shop_profile_url",
    ):
        add(f"raw_profile.{key}", raw_profile.get(key))

    source_video = payload.get("source_video") if isinstance(payload.get("source_video"), dict) else {}
    for key in ("video_url", "title", "description"):
        add(f"source_video.{key}", source_video.get(key), limit=20_000)

    list_item = shop.get("list_item") if isinstance(shop.get("list_item"), dict) else {}
    for key in ("card_visible_text", "handle", "display_name", "source_page_url"):
        add(f"tiktok_shop.list_item.{key}", list_item.get(key), limit=80_000)
    raw_capture = shop.get("raw_capture") if isinstance(shop.get("raw_capture"), dict) else {}
    add("tiktok_shop.raw_capture.page_title", raw_capture.get("page_title"), limit=1_000)
    add("tiktok_shop.raw_visible_text", shop.get("raw_visible_text"), limit=300_000)
    return entries


def _shop_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in re.split(r"[\r\n]+", text or ""):
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        out.append(line[:300])
    return out


def _is_shop_section(value: str) -> bool:
    lower = value.strip().lower()
    return lower in {name.lower() for name in (
        "Sales", "Video", "LIVE", "Followers", "Trends", "Rating", "Audience",
        "Example videos", "Similar creators", "Promotion Performance Score (PPS)",
        "Sample score", "Collaboration metrics", "Gender", "Age", "Top 5 locations",
        "GMV", "GPM", "Items sold", "Products", "Brand collaborations",
    )}


def _looks_money(value: str) -> bool:
    return bool(re.match(r"^\$\d", value.strip()))


def _looks_percent(value: str) -> bool:
    return bool(re.match(r"^\d[\d,.]*(?:\.\d+)?\s*%$", value.strip()))


def _looks_count_value(value: str) -> bool:
    return bool(SHOP_VALUE_RE.match(value.strip())) and not _is_shop_section(value)


def _looks_score(value: str) -> bool:
    return bool(SHOP_SCORE_RE.match(value.strip()))


def _value_after_label(lines: list[str], label: str, predicate, *, max_scan: int = 5) -> str:
    label_key = label.lower()
    for idx, line in enumerate(lines):
        if line.lower() != label_key:
            continue
        for value in lines[idx + 1: idx + 1 + max_scan]:
            if predicate(value):
                return value
            if _is_shop_section(value) and value.lower() != label_key:
                break
    return ""


def _shop_category(lines: list[str]) -> str:
    for label in ("Categories", "GMV by product category"):
        value = _value_after_label(
            lines,
            label,
            lambda v: not _is_shop_section(v) and not v.startswith(",") and not _looks_count_value(v),
            max_scan=6,
        )
        if value:
            return value
    return ""


def _first_score(lines: list[str]) -> str:
    for line in lines:
        if re.match(r"^\d+(?:\.\d+)?\s*/\s*5(?:\.0)?$", line):
            return line
    return ""


def _shop_gender(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for idx, line in enumerate(lines):
        if line.lower() != "gender":
            continue
        window = lines[idx + 1: idx + 8]
        for pos, value in enumerate(window):
            low = value.lower()
            if low == "male":
                pct = next((candidate for candidate in window[pos + 1: pos + 4] if _looks_percent(candidate)), "")
                if pct:
                    out["male_pct_raw"] = pct
            if low == "female":
                pct = next((candidate for candidate in window[pos + 1: pos + 4] if _looks_percent(candidate)), "")
                if pct:
                    out["female_pct_raw"] = pct
        if out:
            break
    return out


def _should_replace_followers(existing: Any, incoming: Any) -> bool:
    incoming_count = parse_followers_count(str(incoming or ""))
    if incoming_count is None:
        return False
    existing_count = parse_followers_count(str(existing or ""))
    if existing_count is None:
        return True
    return existing_count < 1000 <= incoming_count or existing_count < incoming_count / 10


def _handle_from_urls(payload: dict[str, Any], creator: dict[str, Any], shop: dict[str, Any]) -> str:
    source_video = payload.get("source_video") if isinstance(payload.get("source_video"), dict) else {}
    raw_capture = shop.get("raw_capture") if isinstance(shop.get("raw_capture"), dict) else {}
    candidates = [
        creator.get("profile_url"),
        creator.get("url"),
        creator.get("source_url"),
        payload.get("current_url"),
        payload.get("source_url"),
        source_video.get("video_url"),
        *_iter_link_values(raw_capture.get("links")),
    ]
    for value in candidates:
        handle = _handle_from_url(value)
        if handle:
            return handle
    title = str(raw_capture.get("page_title") or "")
    if "|" in title:
        handle = _clean_handle(title.split("|", 1)[0])
        if handle:
            return handle
    return ""


def _handle_from_url(value: Any) -> str:
    if not value:
        return ""
    match = TIKTOK_HANDLE_RE.search(str(value))
    return _clean_handle(match.group("handle")) if match else ""


def _handle_from_text(text: str) -> str:
    if not text:
        return ""
    for match in AT_HANDLE_RE.finditer(text):
        handle = _clean_handle(match.group("handle"))
        if handle:
            return handle
    return ""


def _clean_handle(value: Any) -> str:
    if value is None:
        return ""
    handle = str(value).strip().lstrip("@").split("?", 1)[0].split("/", 1)[0]
    handle = handle.strip().strip(".,;:()[]{}<>\"'")
    if not handle or len(handle) > 100:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,99}", handle):
        return ""
    if handle.lower() in HANDLE_STOPWORDS:
        return ""
    return handle


def _extract_emails(text: str) -> list[str]:
    return _merge_unique(match.group(0).lower() for match in EMAIL_RE.finditer(text or ""))


def _extract_links(text: str) -> list[str]:
    return [_normal_url(match.group(0)) for match in URL_RE.finditer(text or "")]


def _extract_followers_raw(text: str) -> str:
    for regex in (FOLLOWERS_BEFORE_RE, FOLLOWERS_AFTER_RE):
        match = regex.search(text or "")
        if match:
            return f"{match.group('num')}{match.group('suffix') or ''}".replace(",", "")
    return ""


def _existing_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json

                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return [raw]
            return _existing_values(parsed)
        return [raw]
    if isinstance(value, dict):
        return [str(v).strip() for v in value.values() if str(v).strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _iter_link_values(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                import json

                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return [raw]
            return _iter_link_values(parsed)
        return [raw]
    if isinstance(value, dict):
        out = []
        for key in ("url", "href", "link", "profile_url", "value", "source_page_url"):
            if value.get(key):
                out.append(str(value[key]).strip())
        return out
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_iter_link_values(item))
        return out
    return []


def _iter_shop_links(shop: dict[str, Any]) -> list[str]:
    out: list[str] = []
    list_item = shop.get("list_item") if isinstance(shop.get("list_item"), dict) else {}
    raw_capture = shop.get("raw_capture") if isinstance(shop.get("raw_capture"), dict) else {}
    out.extend(_iter_link_values(list_item.get("source_page_url")))
    out.extend(_iter_link_values(shop.get("source_page_url")))
    out.extend(_iter_link_values(raw_capture.get("links")))
    return out


def _merge_unique(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_unique_links(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = _normal_url(value)
        if not url or _is_tiktok_internal_url(url):
            continue
        key = url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out


def _normal_url(value: Any) -> str:
    url = str(value or "").strip().strip(".,;:()[]{}<>\"'，。；、（）【】")
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("www."):
        return f"https://{url}"
    if re.match(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}/", url):
        return f"https://{url}"
    return ""


def _is_tiktok_internal_url(url: str) -> bool:
    lower = url.lower()
    return "tiktok.com" in lower or "tiktokcdn.com" in lower


def _profile_text_excerpt(entries: list[tuple[str, str]]) -> str:
    profile_entries = [
        (name, value)
        for name, value in entries
        if not name.endswith("_url") and not name.endswith(".video_url") and not name.endswith(".source_page_url")
    ]
    text = _compact_text_excerpt(profile_entries, max_chars=1_200)
    if not text:
        return ""
    lines: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or len(line) > 220:
            continue
        lower = line.lower()
        if lower in BIO_SKIP_LINES:
            continue
        if lower in seen:
            continue
        seen.add(lower)
        lines.append(line)
        if len(lines) >= 10:
            break
    return "\n".join(lines)[:1_200]


def _compact_text_excerpt(entries: list[tuple[str, str]], max_chars: int = 2_000) -> str:
    parts: list[str] = []
    used = 0
    for _, value in entries:
        if not value:
            continue
        compact = "\n".join(line.strip() for line in value.splitlines() if line.strip())
        if not compact:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunk = compact[:remaining]
        parts.append(chunk)
        used += len(chunk)
    return "\n".join(parts).strip()


def _shop_list_value(shop: dict[str, Any], key: str) -> Any:
    list_item = shop.get("list_item") if isinstance(shop.get("list_item"), dict) else {}
    return list_item.get(key)


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        parsed = parse_followers_count(value)
        return parsed
    return None
