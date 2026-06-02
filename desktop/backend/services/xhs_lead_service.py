"""Xiaohongshu / Douyin social-lead ingest + GPT purchase-intent judge (Phase 3).

Ports the standalone xhs_cleaning pipeline into the X9 desktop backend: accepts
the browser extension's collection snapshot, cleans + dedups + extracts contacts,
and writes into the x9db `xhs_*` tables (SQLAlchemy models) with a
`department_code`. The GPT judge (prompt_version xhs-b2b-us-dropship-fit-v5)
classifies users as US dropship/sourcing customers; it no-ops without
`OPENAI_API_KEY` so ingest never depends on it.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from urllib.parse import unquote

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.social_lead import (
    XhsAiJudgment,
    XhsCollectionRun,
    XhsComment,
    XhsExtractedContact,
    XhsNoteMedia,
    XhsNote,
    XhsRawSnapshot,
    XhsUser,
    XhsUserHistoryPost,
    XhsUserSource,
)
from ..services.departments import DEFAULT_DEPARTMENT
from ..services.upload_queue_cleanup import attach_queue_cleanup
from ..utils.xhs_cleaning import (
    canonical_url,
    clean_text,
    data_quality_comment,
    data_quality_note,
    data_quality_user,
    extract_contacts,
    extract_douyin_post_id,
    extract_douyin_user_id,
    extract_platform_signals,
    extract_xhs_note_id,
    extract_xhs_user_id,
    parse_count_text,
    platform_prefixed_id,
    stable_hash,
)

PROMPT_VERSION = "xhs-b2b-us-dropship-fit-v6"

NEED_KEYWORDS = (
    "无货源", "没有货源", "没货源", "找货源", "求货源", "货源怎么找", "求推荐货源",
    "想做跨境", "想做电商", "想开店", "想开网店", "新手", "小白", "怎么做跨境",
    "怎么做电商", "想做", "求带", "副业",
)
STRONG_NEED_KEYWORDS = ("无货源", "没有货源", "没货源", "找货源", "求货源", "货源怎么找", "求推荐货源")
ACTIVE_SELLER_KEYWORDS = (
    "亚马逊", "amazon", "temu", "tiktok shop", "tk shop", "shopify", "独立站", "美区",
    "跨境卖家", "店铺", "出单", "爆单", "选品", "运营", "开店", "电商实战",
)
LOGISTICS_KEYWORDS = ("物流", "货代", "报关", "清关", "海外仓", "头程", "尾程", "fba", "仓储", "快递")
SUPPLIER_KEYWORDS = (
    "源头工厂", "厂家", "供应商", "批发", "供货", "一件代发", "代发服务", "支持代发",
    "招代理", "招商", "档口", "工厂直供", "你卖我发货", "可代发", "拿货",
)
TRAINING_KEYWORDS = ("培训", "课程", "割韭菜", "学费", "陪跑", "私教", "训练营", "招商加盟")
CONSUMER_KEYWORDS = ("自用", "求链接", "在哪里买", "好看", "种草", "晒单", "买过", "已下单")


def _uid() -> str:
    return uuid.uuid4().hex


def _parse_dt(value: Any) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00") if text.endswith("Z") else text
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.fromisoformat(text) if fmt is None else datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _dept(payload: dict[str, Any], department_code: str | None) -> str:
    return department_code or payload.get("department_code") or DEFAULT_DEPARTMENT


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _decode_for_scoring(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return unquote(text)
    except Exception:
        return text


def _keyword_hits(text: str, words: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    hits: list[str] = []
    for word in words:
        if word.lower() in lower and word not in hits:
            hits.append(word)
    return hits


def _fit_level(score: int | None) -> str:
    score = int(score or 0)
    if score >= 80:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 40:
        return "low"
    return "irrelevant"


def _rule_priority(decision: str, score: int) -> str:
    if decision == "target_customer" and score >= 90:
        return "A+"
    if decision == "target_customer":
        return "A"
    if decision == "experienced_seller":
        return "B"
    if decision == "logistics_partner":
        return "C"
    if decision == "supplier_peer":
        return "D"
    return "E"


def _rule_based_judge(user: XhsUser, texts: list[str]) -> dict[str, Any]:
    evidence_text = "\n".join(_decode_for_scoring(v) for v in texts if _decode_for_scoring(v))
    profile_text = " ".join(
        _decode_for_scoring(v)
        for v in [user.username_clean, user.account_clean, user.bio_clean, user.last_keyword, evidence_text]
        if _decode_for_scoring(v)
    )
    hits = {
        "need": _keyword_hits(profile_text, NEED_KEYWORDS),
        "strong_need": _keyword_hits(profile_text, STRONG_NEED_KEYWORDS),
        "active_seller": _keyword_hits(profile_text, ACTIVE_SELLER_KEYWORDS),
        "logistics": _keyword_hits(profile_text, LOGISTICS_KEYWORDS),
        "supplier": _keyword_hits(profile_text, SUPPLIER_KEYWORDS),
        "training": _keyword_hits(profile_text, TRAINING_KEYWORDS),
        "consumer": _keyword_hits(profile_text, CONSUMER_KEYWORDS),
    }

    has_need = bool(hits["need"])
    has_strong_need = bool(hits["strong_need"])
    has_active = bool(hits["active_seller"])
    has_logistics = bool(hits["logistics"])
    has_supplier = bool(hits["supplier"])
    has_training = bool(hits["training"])
    has_consumer = bool(hits["consumer"])

    decision = "irrelevant"
    intent_type = "other"
    score = 20
    cap = 100
    reason = "没有明显跨境电商采购、货源或合作需求证据。"

    if has_training:
        decision = "irrelevant"
        intent_type = "training_agency"
        score = 25
        cap = 39
        reason = "命中培训/课程/陪跑类信号，不作为一件代发客户优先跟进。"
    elif has_supplier and not (has_strong_need or has_active):
        decision = "supplier_peer"
        intent_type = "peer_supplier"
        score = 38
        cap = 49
        reason = "更像源头工厂、批发商、供应商或提供一件代发的一方，按同行/上游处理。"
    elif has_logistics and not (has_need or has_active):
        decision = "logistics_partner"
        intent_type = "logistics_partner"
        score = 56
        cap = 64
        reason = "命中物流、货代、海外仓等合作伙伴信号，排在客户线索之后。"
    elif has_strong_need:
        decision = "target_customer"
        intent_type = "no_source_starter"
        score = 95 if has_active else 92
        reason = "明确出现无货源、找货源、求货源等需求，是一件代发商家最优先客户。"
    elif has_need:
        decision = "target_customer"
        intent_type = "sourcing_need"
        score = 84
        reason = "出现想做跨境/电商小白/新手/开店等意向，适合主动确认货源需求。"
    elif has_active:
        decision = "experienced_seller"
        intent_type = "active_cross_border_seller"
        score = 72
        reason = "已有跨境或电商平台、店铺、选品、运营等经验，作为第二优先客户。"
    elif has_logistics:
        decision = "logistics_partner"
        intent_type = "logistics_partner"
        score = 54
        cap = 64
        reason = "有物流/货代相关信号，可进入合作伙伴队列。"
    elif has_supplier:
        decision = "supplier_peer"
        intent_type = "peer_supplier"
        score = 35
        cap = 49
        reason = "出现供货/批发/工厂/代发服务信号，按上游或同行线索处理。"
    elif has_consumer:
        decision = "irrelevant"
        intent_type = "consumer"
        score = 20
        cap = 34
        reason = "更像消费种草或自用购买语境。"

    score = min(score, cap)
    return {
        "fit_score": score,
        "fit_level": _fit_level(score),
        "decision": decision,
        "intent_type": intent_type,
        "customer_priority": _rule_priority(decision, score),
        "hard_cap": cap,
        "reason": reason,
        "hits": hits,
    }


def _compact_judge_texts(texts: list[str], *, limit: int = 20, max_chars: int = 280) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in texts:
        text = _decode_for_scoring(value)
        if not text:
            continue
        text = " ".join(text.split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text[:max_chars])
        if len(out) >= limit:
            break
    return out


def _normalize_judge_result(parsed: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    out = dict(parsed or {})
    try:
        score = int(round(float(out.get("fit_score")))) if out.get("fit_score") is not None else int(rule["fit_score"])
    except (TypeError, ValueError):
        score = int(rule["fit_score"])

    rule_decision = str(rule.get("decision") or "irrelevant")
    cap = int(rule.get("hard_cap") or 100)
    hard_decisions = {"supplier_peer", "logistics_partner", "irrelevant"}
    if rule_decision in hard_decisions:
        score = min(score, cap)
        out["decision"] = rule_decision
        out["intent_type"] = rule.get("intent_type")
    elif rule_decision == "target_customer":
        score = max(score, int(rule["fit_score"]))
        out["decision"] = "target_customer"
        out["intent_type"] = out.get("intent_type") or rule.get("intent_type")
    elif rule_decision == "experienced_seller" and out.get("decision") in {None, "", "potential", "irrelevant"}:
        score = max(score, int(rule["fit_score"]))
        out["decision"] = "experienced_seller"
        out["intent_type"] = rule.get("intent_type")

    score = max(0, min(100, score))
    decision = clean_text(out.get("decision")) or rule_decision
    out["fit_score"] = score
    out["fit_level"] = clean_text(out.get("fit_level")) or _fit_level(score)
    if out["fit_level"] not in {"high", "medium", "low", "irrelevant"}:
        out["fit_level"] = _fit_level(score)
    out["decision"] = decision
    out["intent_type"] = clean_text(out.get("intent_type")) or rule.get("intent_type")
    out["customer_priority"] = clean_text(out.get("customer_priority")) or _rule_priority(decision, score)
    out["rule_signals"] = rule
    out["evidence"] = clean_text(out.get("evidence")) or rule.get("reason")
    out["suggestion"] = clean_text(out.get("suggestion")) or _suggestion_for_decision(decision)
    return out


def _suggestion_for_decision(decision: str) -> str:
    return {
        "target_customer": "优先私信确认正在做的平台、目标市场、缺货源品类，并介绍一件代发合作方式。",
        "experienced_seller": "询问当前店铺平台、主卖品类和供应链痛点，推荐可代发新品或补充货源。",
        "logistics_partner": "进入物流伙伴队列，确认线路、价格、时效和可服务区域。",
        "supplier_peer": "按供应商/同行归档，除非需要补充上游货源，否则不进入客户优先跟进。",
        "irrelevant": "暂不跟进。",
    }.get(decision, "进一步确认真实业务需求后再决定是否跟进。")


def _keyword(payload: dict[str, Any], row: dict[str, Any] | None = None) -> str | None:
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    row = row or {}
    return clean_text(row.get("keyword") or settings.get("keyword") or payload.get("keyword"))


def _external_user_id(raw: dict[str, Any], platform: str) -> str | None:
    profile_url = canonical_url(raw.get("profile_url") or raw.get("canonical_profile_url"))
    if platform == "douyin":
        return clean_text(
            raw.get("external_user_id")
            or raw.get("user_id")
            or raw.get("sec_uid")
            or raw.get("unique_id")
            or raw.get("account")
        ) or extract_douyin_user_id(profile_url)
    return clean_text(
        raw.get("external_user_id")
        or raw.get("xhs_user_id")
        or raw.get("user_id")
        or raw.get("account")
    ) or extract_xhs_user_id(profile_url)


def _external_post_id(raw: dict[str, Any], platform: str) -> str | None:
    url = raw.get("url") or raw.get("post_url") or raw.get("note_url") or raw.get("search_result_url")
    if platform == "douyin":
        return clean_text(raw.get("external_post_id") or raw.get("post_id") or raw.get("video_id") or raw.get("aweme_id")) or extract_douyin_post_id(url)
    return clean_text(raw.get("external_post_id") or raw.get("xhs_note_id") or raw.get("note_id")) or extract_xhs_note_id(url)


def _external_comment_id(raw: dict[str, Any], platform: str) -> str | None:
    value = clean_text(raw.get("external_comment_id") or raw.get("xhs_comment_id") or raw.get("comment_id"))
    if value:
        return value
    return stable_hash([platform, raw.get("note_id") or raw.get("post_id"), raw.get("content"), raw.get("published_at_text"), raw.get("user", {})])[:32]


def _identity_key(value: Any) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    key = text.strip().lstrip("@").replace(" ", "").lower()
    return key or None


def _normalized_identity_column(column):
    return func.replace(func.replace(func.lower(func.coalesce(column, "")), "@", ""), " ", "")


def _cache_identity_keys(platform: str, dept: str, values: list[Any]) -> list[str]:
    prefix = f"{dept}:{platform}:"
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _identity_key(value)
        if not key or key in seen:
            continue
        keys.append(prefix + key)
        seen.add(key)
    return keys


def _first_user_by_identity(
    db: Session,
    *,
    platform: str,
    dept: str,
    values: list[Any],
) -> XhsUser | None:
    """Find an existing cleaned user by stable account identifiers before insert."""
    columns = (
        XhsUser.account_clean,
        XhsUser.account,
        XhsUser.account_raw,
        XhsUser.user_id,
        XhsUser.xhs_user_id,
        XhsUser.external_user_id,
    )
    base_filters = [XhsUser.platform == platform, XhsUser.department_code == dept]
    seen: set[str] = set()
    for value in values:
        key = _identity_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        for column in columns:
            user = db.scalar(
                select(XhsUser)
                .where(*base_filters, _normalized_identity_column(column) == key)
                .order_by(XhsUser.created_at.asc())
                .limit(1)
            )
            if user is not None:
                return user
    return None


def _platform_handle_type(platform: str | None) -> str:
    return "douyin_handle" if (platform or "").lower() == "douyin" else "xhs_handle"


def _source_hash(payload: dict[str, Any]) -> str:
    return stable_hash(payload)


def _upsert_user(
    db: Session,
    cache: dict[str, XhsUser],
    *,
    platform: str,
    dept: str,
    raw: dict[str, Any],
    now: datetime,
    run_id: str | None = None,
    keyword: str | None = None,
) -> XhsUser | None:
    if not isinstance(raw, dict):
        return None
    ext = _external_user_id(raw, platform)
    profile_url = canonical_url(raw.get("profile_url") or raw.get("canonical_profile_url"))
    username = clean_text(raw.get("username") or raw.get("nickname"))
    account = clean_text(raw.get("account") or raw.get("account_raw") or raw.get("unique_id"))
    if not ext and not profile_url and not username and not account:
        return None
    xhs_user_id = platform_prefixed_id(platform, ext or raw.get("xhs_user_id") or profile_url or username or account)
    identity_values = [
        ext,
        xhs_user_id,
        raw.get("external_user_id"),
        raw.get("xhs_user_id"),
        raw.get("user_id"),
        raw.get("sec_uid"),
        raw.get("unique_id"),
        raw.get("account"),
        raw.get("account_raw"),
        account,
        profile_url,
    ]
    cache_keys = _cache_identity_keys(platform, dept, identity_values + [username])
    user = None
    for cache_key in cache_keys:
        user = cache.get(cache_key)
        if user is not None:
            break
    if user is None and ext:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.external_user_id == ext))
    if user is None and xhs_user_id:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.department_code == dept, XhsUser.xhs_user_id == xhs_user_id))
    if user is None and profile_url:
        user = db.scalar(select(XhsUser).where(XhsUser.platform == platform, XhsUser.department_code == dept, XhsUser.canonical_profile_url == profile_url))
    if user is None:
        user = _first_user_by_identity(db, platform=platform, dept=dept, values=identity_values)
    if user is None:
        user = XhsUser(id=_uid(), platform=platform, department_code=dept, external_user_id=ext, first_seen_at=now)
        db.add(user)
    # update fields (new value wins, keep old otherwise)
    user.department_code = dept or user.department_code
    user.external_user_id = ext or user.external_user_id
    user.xhs_user_id = xhs_user_id or user.xhs_user_id
    user.user_id = clean_text(raw.get("user_id")) or user.user_id
    user.username = username or user.username
    user.username_raw = username or user.username_raw
    user.username_clean = username or user.username_clean
    user.account = account or user.account
    user.account_raw = account or user.account_raw
    user.account_clean = account or user.account_clean
    user.profile_url = profile_url or user.profile_url
    user.canonical_profile_url = profile_url or user.canonical_profile_url
    user.avatar_url = clean_text(raw.get("avatar_url") or raw.get("avatar")) or user.avatar_url
    bio = clean_text(raw.get("bio") or raw.get("desc") or raw.get("signature"))
    user.bio = bio or user.bio
    user.bio_raw = bio or user.bio_raw
    user.bio_clean = bio or user.bio_clean
    user.location_text = clean_text(raw.get("location") or raw.get("location_text") or raw.get("ip_location")) or user.location_text
    user.gender_text = clean_text(raw.get("gender") or raw.get("gender_text")) or user.gender_text
    stats_text = " ".join(str(x) for x in _list(raw.get("stats_text")))
    follower_text = raw.get("follower_count") or raw.get("follower_count_text") or raw.get("fans") or raw.get("fans_count")
    following_text = raw.get("following_count") or raw.get("following_count_text")
    liked_text = raw.get("liked_collect_count") or raw.get("liked_collect_count_text")
    note_text = raw.get("note_count") or raw.get("note_count_text")
    if not follower_text and "粉丝" in stats_text:
        follower_text = stats_text
    if not following_text and "关注" in stats_text:
        following_text = stats_text
    if not liked_text and ("获赞" in stats_text or "喜欢" in stats_text):
        liked_text = stats_text
    fc = parse_count_text(follower_text)
    if fc is not None:
        user.follower_count = fc
        user.followers_count = fc
    if follower_text:
        user.follower_count_text = clean_text(follower_text) or user.follower_count_text
    following = parse_count_text(following_text)
    if following is not None:
        user.following_count = following
    if following_text:
        user.following_count_text = clean_text(following_text) or user.following_count_text
    liked = parse_count_text(liked_text)
    if liked is not None:
        user.liked_collect_count = liked
    if liked_text:
        user.liked_collect_count_text = clean_text(liked_text) or user.liked_collect_count_text
    note_count = parse_count_text(note_text)
    if note_count is not None:
        user.note_count = note_count
    if note_text:
        user.note_count_text = clean_text(note_text) or user.note_count_text
    if raw.get("history_posts") is not None:
        user.history_posts_json = _dump_json(_list(raw.get("history_posts")))
    if raw.get("sources") is not None:
        user.sources_json = _dump_json(_list(raw.get("sources")))
    user.raw_json = _dump_json(raw)
    user.last_keyword = keyword or user.last_keyword
    user.platform_signals = _dump_json(extract_platform_signals([username, account, bio, stats_text]))
    user.profile_quality = _dump_json(data_quality_user(raw))
    user.first_seen_run_id = run_id or user.first_seen_run_id
    user.profile_collected_at = _parse_dt(raw.get("profile_collected_at")) or user.profile_collected_at
    user.clean_status = "cleaned"
    user.last_seen_at = now
    db.flush()
    _add_platform_contact(db, dept=dept, user=user)
    for cache_key in cache_keys:
        cache[cache_key] = user
    return user


def _add_contacts(db: Session, *, dept: str, owner_type: str, owner_id: str, user: XhsUser | None, texts: list[Any]) -> int:
    contacts = extract_contacts(texts)
    if not contacts:
        return 0
    added = 0
    for c in contacts:
        exists = db.scalar(
            select(XhsExtractedContact.id).where(
                XhsExtractedContact.owner_type == owner_type,
                XhsExtractedContact.owner_id == owner_id,
                XhsExtractedContact.contact_type == c["contact_type"],
                XhsExtractedContact.value_norm == c["value_norm"],
            )
        )
        if exists:
            continue
        db.add(XhsExtractedContact(
            id=_uid(), department_code=dept, owner_type=owner_type, owner_id=owner_id,
            user_id=user.id if user else None,
            contact_type=c["contact_type"], value_raw=c["value_raw"], value_norm=c["value_norm"],
            source_field=owner_type, rule_code=c["rule_code"],
        ))
        added += 1
    if added and user is not None:
        user.has_contact = 1
    return added


def _add_platform_contact(db: Session, *, dept: str, user: XhsUser) -> int:
    raw = clean_text(user.account_clean or user.xhs_user_id or user.username_clean)
    norm = clean_text(user.account_clean or user.xhs_user_id or user.external_user_id)
    if not raw or not norm:
        return 0
    contact_type = _platform_handle_type(user.platform)
    exists = db.scalar(
        select(XhsExtractedContact).where(
            XhsExtractedContact.owner_type == "user",
            XhsExtractedContact.owner_id == user.id,
            XhsExtractedContact.contact_type.in_((contact_type, "platform_handle")),
            XhsExtractedContact.value_norm == norm.lower(),
        )
    )
    if exists:
        exists.contact_type = contact_type
        exists.rule_code = f"{user.platform or 'xhs'}_account"
        user.has_contact = 1
        return 0
    db.add(
        XhsExtractedContact(
            id=_uid(),
            department_code=dept,
            owner_type="user",
            owner_id=user.id,
            user_id=user.id,
            contact_type=contact_type,
            value_raw=raw,
            value_norm=norm.lower(),
            source_field="account_clean" if user.account_clean else "xhs_user_id",
            rule_code=f"{user.platform or 'xhs'}_account",
        )
    )
    user.has_contact = 1
    return 1


def _add_note_media(db: Session, *, dept: str, note: XhsNote, raw: dict[str, Any]) -> int:
    rows: list[tuple[str, str]] = []
    cover = clean_text(raw.get("cover_url"))
    if cover:
        rows.append(("cover", cover))
    for value in _list(raw.get("image_urls")):
        url = clean_text(value)
        if url:
            rows.append(("image", url))
    for value in _list(raw.get("media_urls")):
        url = clean_text(value)
        if url:
            rows.append(("video", url))
    media_url = clean_text(raw.get("media_url"))
    if media_url:
        rows.append(("video", media_url))
    added = 0
    seen: set[str] = set()
    for position, (media_type, url) in enumerate(rows):
        if url in seen:
            continue
        seen.add(url)
        exists = db.scalar(select(XhsNoteMedia.id).where(XhsNoteMedia.note_id == note.id, XhsNoteMedia.url == url))
        if exists:
            continue
        db.add(
            XhsNoteMedia(
                id=_uid(),
                department_code=dept,
                note_id=note.id,
                media_type=media_type,
                url=url,
                normalized_url=canonical_url(url),
                position=position,
            )
        )
        added += 1
    return added


def _add_user_source(
    db: Session,
    *,
    dept: str,
    platform: str,
    user: XhsUser,
    run_id: str | None,
    note_id: str | None,
    comment_id: str | None,
    source_type: str,
    keyword: str | None,
    evidence_text: Any,
    evidence_url: Any,
    evidence_images: list[Any] | None = None,
    comment_depth: int | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    record = {
        "user_id": user.id,
        "run_id": run_id,
        "note_id": note_id,
        "comment_id": comment_id,
        "source_type": source_type,
        "keyword": keyword,
        "evidence_text": clean_text(evidence_text),
        "evidence_url": canonical_url(evidence_url),
    }
    digest = _source_hash(record)
    exists = db.scalar(select(XhsUserSource.id).where(XhsUserSource.source_hash == digest))
    if exists:
        return 0
    db.add(
        XhsUserSource(
            id=_uid(),
            department_code=dept,
            platform=platform,
            user_id=user.id,
            run_id=run_id,
            note_id=note_id,
            comment_id=comment_id,
            source_type=source_type,
            keyword=keyword,
            evidence_text=record["evidence_text"],
            evidence_url=record["evidence_url"],
            evidence_images=_dump_json(evidence_images or []),
            comment_depth=comment_depth,
            source_payload=_dump_json(payload or {}),
            source_hash=digest,
        )
    )
    return 1


def _add_history_posts(db: Session, *, dept: str, platform: str, user: XhsUser, raw: dict[str, Any]) -> int:
    added = 0
    for position, post in enumerate(_list(raw.get("history_posts"))):
        if not isinstance(post, dict):
            continue
        url = canonical_url(post.get("url") or post.get("post_url"))
        post_id = _external_post_id(post, platform) or (stable_hash(url)[:24] if url else None)
        xhs_note_id = platform_prefixed_id(platform, post_id or url)
        exists = None
        if xhs_note_id:
            exists = db.scalar(
                select(XhsUserHistoryPost.id).where(
                    XhsUserHistoryPost.user_id == user.id,
                    XhsUserHistoryPost.xhs_note_id == xhs_note_id,
                )
            )
        if exists:
            continue
        db.add(
            XhsUserHistoryPost(
                id=_uid(),
                department_code=dept,
                platform=platform,
                user_id=user.id,
                xhs_note_id=xhs_note_id,
                canonical_note_url=url,
                title_raw=clean_text(post.get("title")),
                title_clean=clean_text(post.get("title")),
                cover_url=clean_text(post.get("cover_url")),
                like_count_text=clean_text(post.get("like_count_text")),
                like_count=parse_count_text(post.get("like_count") or post.get("like_count_text")),
                published_at_text=clean_text(post.get("published_at_text")),
                position=position,
            )
        )
        added += 1
    return added


def ingest_snapshot(db: Session, payload: dict[str, Any], *, platform: str | None = None, department_code: str | None = None) -> dict[str, Any]:
    platform = (payload.get("platform") or platform or "xhs").strip().lower()
    dept = _dept(payload, department_code)
    now = datetime.utcnow()
    keyword = _keyword(payload)

    # collection run (upsert by run_key)
    run_key = clean_text(payload.get("run_id")) or stable_hash(payload)[:24]
    run = None
    if run_key:
        run = db.scalar(select(XhsCollectionRun).where(XhsCollectionRun.run_key == run_key))
    if run is None:
        run = XhsCollectionRun(id=_uid(), department_code=dept, platform=platform, run_key=run_key)
        db.add(run)
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    run.department_code = dept
    run.platform = platform
    run.keyword = keyword or run.keyword
    run.source_page_url = canonical_url(payload.get("source_page_url")) or run.source_page_url
    run.plugin_version = clean_text(payload.get("plugin_version")) or run.plugin_version
    run.collector_version = clean_text(payload.get("collector_version")) or run.collector_version
    run.raw_settings = _dump_json(settings)
    run.status = clean_text(payload.get("status")) or "done"
    run.started_at = _parse_dt(payload.get("started_at")) or run.started_at
    run.finished_at = _parse_dt(payload.get("finished_at")) or run.finished_at
    db.flush()

    # raw snapshot audit
    try:
        raw_json = json.dumps(payload, ensure_ascii=False, default=str)
        db.add(XhsRawSnapshot(
            id=_uid(), department_code=dept, platform=platform, run_id=run.id,
            snapshot_type="search", external_id=run_key, source_url=run.source_page_url,
            payload=raw_json, payload_hash=stable_hash(payload), clean_status="cleaned", observed_at=now,
        ))
    except Exception:  # noqa: BLE001 - audit row must never block ingest
        pass

    user_cache: dict[str, XhsUser] = {}
    note_cache: dict[str, XhsNote] = {}
    comment_cache: dict[str, XhsComment] = {}
    pending_parent_updates: list[tuple[XhsComment, str | None]] = []
    counts = {"notes": 0, "comments": 0, "users": 0, "contacts": 0, "media": 0, "history_posts": 0, "user_sources": 0}

    # top-level user profiles (rich: bio, followers)
    for raw in payload.get("users") or []:
        u = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw, now=now, run_id=run.id, keyword=keyword)
        if u is not None:
            counts["users"] += 1
            counts["history_posts"] += _add_history_posts(db, dept=dept, platform=platform, user=u, raw=raw)
            counts["contacts"] += _add_contacts(
                db, dept=dept, owner_type="user", owner_id=u.id, user=u,
                texts=[u.bio_clean, u.username_clean, u.account_clean, raw.get("signature"), _dump_json(raw.get("stats_text") or [])],
            )
            for src in _list(raw.get("sources")):
                if not isinstance(src, dict):
                    continue
                source_type = clean_text(src.get("source_type")) or "manual"
                if source_type == "comment":
                    source_type = "reply_author" if int(src.get("comment_depth") or 0) > 0 else "comment_author"
                if source_type not in {"post_author", "comment_author", "reply_author", "mentioned_user", "profile_history", "manual"}:
                    source_type = "manual"
                counts["user_sources"] += _add_user_source(
                    db,
                    dept=dept,
                    platform=platform,
                    user=u,
                    run_id=run.id,
                    note_id=None,
                    comment_id=None,
                    source_type=source_type,
                    keyword=clean_text(src.get("keyword")) or keyword,
                    evidence_text=src.get("comment_content") or src.get("note_title") or src.get("post_title"),
                    evidence_url=src.get("note_url") or src.get("post_url"),
                    evidence_images=_list(src.get("note_images")),
                    comment_depth=int(src.get("comment_depth") or 0) if src.get("comment_depth") is not None else None,
                    payload=src,
                )

    # notes / posts
    notes = payload.get("notes") or payload.get("posts") or []
    for raw in notes:
        if not isinstance(raw, dict):
            continue
        row_keyword = _keyword(payload, raw)
        ext_post = _external_post_id(raw, platform)
        canonical_note_url = canonical_url(raw.get("url") or raw.get("canonical_note_url") or raw.get("post_url"))
        author = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("author") or {}, now=now, run_id=run.id, keyword=row_keyword)
        note = None
        if ext_post:
            note = db.scalar(select(XhsNote).where(XhsNote.platform == platform, XhsNote.external_post_id == ext_post))
        if note is None and canonical_note_url:
            note = db.scalar(select(XhsNote).where(XhsNote.platform == platform, XhsNote.canonical_note_url == canonical_note_url))
        if note is None:
            note = XhsNote(id=_uid(), platform=platform, department_code=dept, external_post_id=ext_post, first_seen_at=now)
            db.add(note)
        note.department_code = dept
        note.external_post_id = ext_post or note.external_post_id
        note.xhs_note_id = platform_prefixed_id(platform, ext_post or raw.get("xhs_note_id") or raw.get("aweme_id")) or note.xhs_note_id
        note.note_id = clean_text(raw.get("note_id") or raw.get("post_id")) or note.note_id
        note.content_type = "video" if (raw.get("aweme_id") or platform == "douyin") else "note"
        note.url = canonical_note_url or note.url
        note.canonical_note_url = canonical_note_url or note.canonical_note_url
        note.search_result_url = canonical_url(raw.get("search_result_url") or raw.get("source_page_url")) or note.search_result_url
        note.title = clean_text(raw.get("title")) or note.title
        note.title_raw = clean_text(raw.get("title")) or note.title_raw
        note.title_clean = clean_text(raw.get("title")) or note.title_clean
        note.content = clean_text(raw.get("content") or raw.get("desc")) or note.content
        note.desc_raw = clean_text(raw.get("desc")) or note.desc_raw
        note.desc_clean = clean_text(raw.get("desc")) or note.desc_clean
        note.published_at_text = clean_text(raw.get("published_at_text")) or note.published_at_text
        note.published_at = _parse_dt(raw.get("published_at")) or note.published_at
        note.publish_location = clean_text(raw.get("publish_location") or raw.get("location")) or note.publish_location
        note.like_count_text = clean_text(raw.get("like_count_text") or raw.get("like_count") or raw.get("digg_count")) or note.like_count_text
        note.like_count = parse_count_text(raw.get("like_count") or raw.get("like_count_text") or raw.get("digg_count")) if (raw.get("like_count") or raw.get("like_count_text") or raw.get("digg_count")) is not None else note.like_count
        note.collect_count_text = clean_text(raw.get("collect_count_text") or raw.get("collect_count")) or note.collect_count_text
        note.collect_count = parse_count_text(raw.get("collect_count") or raw.get("collect_count_text")) if (raw.get("collect_count") or raw.get("collect_count_text")) is not None else note.collect_count
        note.comment_count_text = clean_text(raw.get("comment_count_text") or raw.get("comment_count")) or note.comment_count_text
        note.comment_count = parse_count_text(raw.get("comment_count") or raw.get("comment_count_text")) if (raw.get("comment_count") or raw.get("comment_count_text")) is not None else note.comment_count
        note.author_user_id = author.id if author else note.author_user_id
        note.author_xhs_user_id_snapshot = author.xhs_user_id if author else note.author_xhs_user_id_snapshot
        note.author_username = author.username_clean if author else note.author_username
        note.author_username_snapshot = author.username_clean if author else note.author_username_snapshot
        note.cover_url = clean_text(raw.get("cover_url")) or note.cover_url
        note.images_json = _dump_json(_list(raw.get("image_urls"))) if raw.get("image_urls") is not None else note.images_json
        note.tags_json = _dump_json(_list(raw.get("tags"))) if raw.get("tags") is not None else note.tags_json
        note.keyword = row_keyword or note.keyword
        note.content_hash = stable_hash([note.title_clean, note.desc_clean, note.canonical_note_url])
        note.relevance_status = note.relevance_status or "unknown"
        note.data_quality = _dump_json(data_quality_note(raw))
        note.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        note.last_seen_at = now
        db.flush()
        counts["notes"] += 1
        counts["media"] += _add_note_media(db, dept=dept, note=note, raw=raw)
        if author is not None:
            counts["user_sources"] += _add_user_source(
                db,
                dept=dept,
                platform=platform,
                user=author,
                run_id=run.id,
                note_id=note.id,
                comment_id=None,
                source_type="post_author",
                keyword=row_keyword or keyword,
                evidence_text=note.title_clean or note.desc_clean,
                evidence_url=note.canonical_note_url,
                evidence_images=_list(raw.get("image_urls")),
                payload=raw,
            )
            counts["contacts"] += _add_contacts(
                db, dept=dept, owner_type="user", owner_id=author.id, user=author,
                texts=[author.bio_clean, author.username_clean, author.account_clean],
            )
        if ext_post:
            note_cache[ext_post] = note
        if note.xhs_note_id:
            note_cache[note.xhs_note_id] = note
        if canonical_note_url:
            note_cache[canonical_note_url] = note

    # comments (+ commenter users + contacts from comment text)
    for raw in payload.get("comments") or []:
        if not isinstance(raw, dict):
            continue
        row_keyword = _keyword(payload, raw)
        ext_comment = _external_comment_id(raw, platform)
        commenter = _upsert_user(db, user_cache, platform=platform, dept=dept, raw=raw.get("user") or {}, now=now, run_id=run.id, keyword=row_keyword)
        note_lookup = clean_text(raw.get("note_id") or raw.get("post_id")) or ""
        note_url = canonical_url(raw.get("note_url") or raw.get("post_url"))
        note = note_cache.get(note_lookup) or note_cache.get(note_url or "")
        comment = None
        if ext_comment:
            comment = db.scalar(select(XhsComment).where(XhsComment.platform == platform, XhsComment.external_comment_id == ext_comment))
        if comment is None:
            comment = XhsComment(id=_uid(), platform=platform, department_code=dept, external_comment_id=ext_comment, first_seen_at=now)
            db.add(comment)
        comment.department_code = dept
        comment.external_comment_id = ext_comment or comment.external_comment_id
        comment.xhs_comment_id = platform_prefixed_id(platform, ext_comment or raw.get("xhs_comment_id")) or comment.xhs_comment_id
        comment.comment_id = clean_text(raw.get("comment_id")) or comment.comment_id
        comment.note_id = note.id if note else comment.note_id
        comment.note_url = note_url or comment.note_url
        comment.root_comment_id = clean_text(raw.get("root_comment_id")) or comment.root_comment_id
        comment.root_comment_external_id = clean_text(raw.get("root_comment_id")) or comment.root_comment_external_id
        comment.parent_comment_external_id = clean_text(raw.get("parent_comment_id")) or comment.parent_comment_external_id
        comment.user_id = commenter.id if commenter else comment.user_id
        user_raw = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        comment.user_xhs_id_snapshot = commenter.xhs_user_id if commenter else comment.user_xhs_id_snapshot
        comment.username = clean_text(user_raw.get("username") or user_raw.get("nickname")) or comment.username
        comment.username_snapshot = comment.username or (commenter.username_clean if commenter else comment.username_snapshot)
        comment.profile_url = canonical_url(user_raw.get("profile_url")) or comment.profile_url
        comment.profile_url_snapshot = comment.profile_url or comment.profile_url_snapshot
        comment.avatar_url = clean_text(user_raw.get("avatar_url") or user_raw.get("avatar")) or comment.avatar_url
        comment.avatar_url_snapshot = comment.avatar_url or comment.avatar_url_snapshot
        comment.content = clean_text(raw.get("content")) or comment.content
        comment.content_raw = clean_text(raw.get("content")) or comment.content_raw
        comment.content_clean = clean_text(raw.get("content")) or comment.content_clean
        comment.published_at_text = clean_text(raw.get("published_at_text")) or comment.published_at_text
        comment.published_at = _parse_dt(raw.get("published_at")) or comment.published_at
        comment.location = clean_text(raw.get("location")) or comment.location
        comment.location_text = clean_text(raw.get("location") or raw.get("location_text")) or comment.location_text
        comment.like_count_text = clean_text(raw.get("like_count_text") or raw.get("like_count")) or comment.like_count_text
        comment.like_count = parse_count_text(raw.get("like_count") or raw.get("like_count_text")) if (raw.get("like_count") or raw.get("like_count_text")) is not None else comment.like_count
        comment.reply_count = parse_count_text(raw.get("reply_count") or raw.get("reply_count_text")) if (raw.get("reply_count") or raw.get("reply_count_text")) is not None else comment.reply_count
        comment.is_author_reply = 1 if raw.get("is_author_reply") else comment.is_author_reply
        comment.keyword = row_keyword or comment.keyword
        comment.data_quality = _dump_json(data_quality_comment(raw))
        comment.raw_json = json.dumps(raw, ensure_ascii=False, default=str)
        comment.last_seen_at = now
        db.flush()
        counts["comments"] += 1
        if comment.external_comment_id:
            comment_cache[comment.external_comment_id] = comment
        pending_parent_updates.append((comment, clean_text(raw.get("parent_comment_id") or raw.get("root_comment_id"))))
        # contacts live mostly in comment text ("微信 xxx" / "vx: yyy")
        counts["contacts"] += _add_contacts(
            db, dept=dept, owner_type="comment", owner_id=comment.id, user=commenter,
            texts=[comment.content_clean],
        )
        if commenter is not None:
            counts["user_sources"] += _add_user_source(
                db,
                dept=dept,
                platform=platform,
                user=commenter,
                run_id=run.id,
                note_id=note.id if note else None,
                comment_id=comment.id,
                source_type="reply_author" if int(raw.get("depth") or 0) > 0 else "comment_author",
                keyword=row_keyword or keyword,
                evidence_text=comment.content_clean,
                evidence_url=comment.note_url,
                evidence_images=[],
                comment_depth=int(raw.get("depth") or 0),
                payload=raw,
            )

    for comment, parent_external_id in pending_parent_updates:
        parent = comment_cache.get(parent_external_id or "")
        if parent is not None and comment.parent_comment_id is None:
            comment.parent_comment_id = parent.id

    db.commit()
    auto_judgment = request_auto_judge_after_ingest(dept)
    return attach_queue_cleanup(
        {"ok": True, "platform": platform, "run_id": run.id, "counts": counts, "auto_judgment": auto_judgment},
        payload,
        entity="social_snapshot",
        platform=platform,
        run_id=run.id,
        counts=counts,
    )


def request_auto_judge_after_ingest(department_code: str | None = None) -> dict[str, Any]:
    try:
        from ..utils.foreign_trade_scoring_scheduler import request_auto_score

        request_auto_score(department_code)
        return {"queued": True, "department_code": department_code}
    except Exception as exc:  # noqa: BLE001 - auto scoring must never block ingest
        return {"queued": False, "error": str(exc)[:300], "department_code": department_code}


def count_unjudged_social_users(db: Session, department_code: str | None = None) -> int:
    stmt = _unjudged_social_user_stmt(department_code)
    return int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)


def auto_judge_unjudged_social(db: Session, *, department_code: str | None = None, limit: int | None = None) -> dict[str, Any]:
    resolved_limit = _env_int("X9_FT_AUTO_JUDGE_LIMIT", 40, minimum=0, maximum=200)
    if limit is not None:
        resolved_limit = limit
    if resolved_limit <= 0:
        return {"enabled": False, "reason": "disabled", "pending": 0, "judged": 0}
    pending = count_unjudged_social_users(db, department_code)
    if pending <= 0:
        return {"enabled": True, "pending": 0, "judged": 0, "ok": True}
    result = judge_users_with_gpt(db, department_code=department_code, limit=min(resolved_limit, pending), force=False)
    return {"enabled": True, "pending": pending, "limit": resolved_limit, **result}


def _unjudged_social_user_stmt(department_code: str | None = None):
    judged_user_ids = select(XhsAiJudgment.user_id).where(XhsAiJudgment.prompt_version == PROMPT_VERSION)
    stmt = select(XhsUser).where(XhsUser.has_contact == 1, XhsUser.id.not_in(judged_user_ids))
    if department_code:
        stmt = stmt.where(XhsUser.department_code == department_code)
    return stmt


# ---------------- GPT purchase-intent judge ----------------

def _openai_cfg() -> dict[str, str] | None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    return {
        "key": key,
        "base": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
    }


_JUDGE_SYSTEM = (
    "你是给一件代发商家服务的跨境电商 BD 线索判定助手。我们的客户不是供应商，而是需要货源/代发服务的人。\n"
    "优先级：A+ 最优先=想做跨境电商/电商但无货源、正在找货源、求推荐货源、小白新手想开店；"
    "A=有跨境/电商意向，需进一步确认货源需求；B=已经在做亚马逊/Temu/TikTok Shop/Shopify/独立站/国内电商，有选品或供应链优化机会；"
    "C=物流、货代、海外仓、清关等合作伙伴；D=源头工厂、批发、供应商、招商、提供一件代发、招代理等上游/同行；"
    "E=培训课程、陪跑中介、纯消费者、无业务相关内容。\n"
    "硬规则：看到“支持一件代发/源头工厂/厂家直供/批发/招代理/你卖我发货”等，通常是供应方，不得判为 A/A+ 客户；"
    "看到“无货源/没货源/找货源/求货源/想做跨境/小白怎么做/想开网店”等，才是最优先客户。物流公司最多 C 级，培训/课程最多 E 级。\n"
    "只返回 JSON，字段：fit_score(0-100)、fit_level(high/medium/low/irrelevant)、"
    "decision(target_customer/experienced_seller/logistics_partner/supplier_peer/irrelevant)、"
    "intent_type(no_source_starter/sourcing_need/active_cross_border_seller/logistics_partner/peer_supplier/training_agency/consumer/other)、"
    "customer_priority(A+/A/B/C/D/E)、evidence、suggestion。evidence 和 suggestion 用简体中文。"
)


def _judge_one(cfg: dict[str, str], user: XhsUser, texts: list[str]) -> dict[str, Any] | None:
    rule = _rule_based_judge(user, texts)
    evidence_texts = _compact_judge_texts(texts)
    payload = {
        "model": cfg["model"],
        "temperature": 0.1,
        "max_tokens": _env_int("X9_FT_GPT_MAX_TOKENS", 420, minimum=160, maximum=1000),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps({
                "prompt_version": PROMPT_VERSION,
                "username": user.username_clean,
                "account": user.account_clean or user.xhs_user_id,
                "bio": user.bio_clean,
                "follower_count": user.follower_count,
                "location": user.location_text,
                "platform": user.platform,
                "rule_precheck": rule,
                "evidence_texts": evidence_texts,
            }, ensure_ascii=False)},
        ],
    }
    with httpx.Client(timeout=float(os.getenv("OPENAI_TIMEOUT", "30"))) as client:
        resp = client.post(
            f"{cfg['base']}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    parsed = json.loads(content)
    parsed = _normalize_judge_result(parsed, rule)
    return {"parsed": parsed, "raw": content}


def _judge_texts_for_user(db: Session, user: XhsUser) -> list[str]:
    texts: list[str] = [
        user.username_clean or "",
        user.account_clean or "",
        user.bio_clean or "",
        user.last_keyword or "",
    ]
    texts.extend(
        row for row in db.scalars(
            select(XhsComment.content_clean)
            .where(XhsComment.user_id == user.id)
            .order_by(XhsComment.created_at.desc())
            .limit(20)
        ).all() if row
    )
    for keyword, evidence in db.execute(
        select(XhsUserSource.keyword, XhsUserSource.evidence_text)
        .where(XhsUserSource.user_id == user.id)
        .order_by(XhsUserSource.created_at.desc())
        .limit(12)
    ).all():
        if keyword:
            texts.append(str(keyword))
        if evidence:
            texts.append(str(evidence))
    for title, desc in db.execute(
        select(XhsNote.title_clean, XhsNote.desc_clean)
        .where(XhsNote.author_user_id == user.id)
        .order_by(XhsNote.created_at.desc())
        .limit(8)
    ).all():
        if title:
            texts.append(str(title))
        if desc:
            texts.append(str(desc))
    return [t for t in texts if clean_text(t)]


def _judge_user_view(user: XhsUser) -> SimpleNamespace:
    return SimpleNamespace(
        id=user.id,
        department_code=user.department_code,
        platform=user.platform,
        username_clean=user.username_clean,
        account_clean=user.account_clean,
        xhs_user_id=user.xhs_user_id,
        bio_clean=user.bio_clean,
        follower_count=user.follower_count,
        location_text=user.location_text,
        last_keyword=user.last_keyword,
    )


def judge_users_with_gpt(db: Session, *, department_code: str | None = None, limit: int = 10, force: bool = False) -> dict[str, Any]:
    cfg = _openai_cfg()
    if cfg is None:
        return {"ok": False, "error": "OPENAI_API_KEY not configured", "judged": 0}

    stmt = select(XhsUser).where(XhsUser.has_contact == 1) if force else _unjudged_social_user_stmt(department_code)
    if department_code:
        stmt = stmt.where(XhsUser.department_code == department_code)
    candidates = list(db.scalars(stmt.order_by(XhsUser.created_at.desc()).limit(limit)).all())

    jobs: list[tuple[XhsUser, SimpleNamespace, list[str]]] = []
    for user in candidates:
        if len(jobs) >= limit:
            break
        if not force:
            existing = db.scalar(select(XhsAiJudgment.id).where(XhsAiJudgment.user_id == user.id, XhsAiJudgment.prompt_version == PROMPT_VERSION))
            if existing:
                continue
        jobs.append((user, _judge_user_view(user), _judge_texts_for_user(db, user)))

    concurrency = min(_env_int("X9_FT_GPT_CONCURRENCY", 4, minimum=1, maximum=12), max(len(jobs), 1))

    def persist_result(user: XhsUser, result: dict[str, Any] | None, error: Exception | None = None) -> bool:
        if error is not None:
            db.add(XhsAiJudgment(
                id=_uid(), department_code=user.department_code, platform=user.platform, user_id=user.id,
                model=cfg["model"], prompt_version=PROMPT_VERSION, decision="error",
                judgment=None, raw_response=str(error)[:1000],
            ))
            db.commit()
            return False
        p = result["parsed"] if result else {}
        try:
            fit_score = int(round(float(p.get("fit_score")))) if p.get("fit_score") is not None else None
        except (TypeError, ValueError):
            fit_score = None
        db.add(XhsAiJudgment(
            id=_uid(), department_code=user.department_code, platform=user.platform, user_id=user.id,
            model=cfg["model"], prompt_version=PROMPT_VERSION,
            fit_score=fit_score,
            fit_level=clean_text(p.get("fit_level")),
            decision=clean_text(p.get("decision")),
            intent_type=clean_text(p.get("intent_type")),
            judgment=json.dumps(p, ensure_ascii=False),
            raw_response=(result["raw"] if result else None),
        ))
        db.commit()
        return True

    judged = 0
    errors = 0
    if concurrency <= 1 or len(jobs) <= 1:
        for user, view, texts in jobs:
            try:
                result = _judge_one(cfg, view, texts)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                persist_result(user, None, exc)
                continue
            judged += 1 if persist_result(user, result) else 0
        return {"ok": True, "judged": judged, "errors": errors, "concurrency": concurrency}

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="ft-gpt-judge") as executor:
        futures = {
            executor.submit(_judge_one, cfg, view, texts): user
            for user, view, texts in jobs
        }
        for future in as_completed(futures):
            user = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                errors += 1
                persist_result(user, None, exc)
                continue
            judged += 1 if persist_result(user, result) else 0
    return {"ok": True, "judged": judged, "errors": errors, "concurrency": concurrency}
