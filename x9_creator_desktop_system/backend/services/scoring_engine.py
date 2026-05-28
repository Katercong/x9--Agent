"""scoring_engine.py — produces sub-scores + raw evidence per creator.

The recommendation engine consumes `ScoreResult` to form business
decisions. Scoring here is *pure* — no DB writes, no risk gating beyond
score math.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.json_utils import loads_json_list
from ..utils.contact_methods import contact_types_for, has_contact_method
from ..utils.keyword_rules_v3 import (
    ADULT_CARE_KEYWORDS,
    AUDIENCE_BONUS_CAP,
    AUDIENCE_RULES,
    COMMERCE_SIGNAL_KEYWORDS,
    CONTENT_FORMAT_KEYWORDS,
    FEMININE_ADJACENT_CAP,
    FEMININE_ADJACENT_KEYWORDS,
    FEMININE_FORMAT_CAP,
    FEMININE_FORMAT_KEYWORDS,
    FEMININE_SEARCH_KEYWORD_BONUS,
    FEMININE_SEARCH_KEYWORDS,
    FEMININE_STRONG_CAP,
    FEMININE_STRONG_KEYWORDS,
    HEALTH_MASK_KEYWORDS,
    HOME_CARE_KEYWORDS,
    KeywordHit,
    MOM_BABY_KEYWORDS,
    OTHER_CATEGORY_HIT_POINTS,
    PET_CARE_KEYWORDS,
    cap,
    classify_email,
    find_keyword_hits,
    find_simple_keywords,
    follower_scale_score,
    normalize,
    phrase_present,
    pick_feminine_product_bucket,
)


@dataclass
class ScoreResult:
    # Sub-scores
    feminine_care_fit: int = 0
    pet_care_fit: int = 0
    home_care_fit: int = 0
    adult_care_fit: int = 0
    mom_baby_fit: int = 0
    health_mask_fit: int = 0
    primary_product_category: str = "general_lifestyle"
    primary_product_fit_score: int = 0
    suggested_feminine_bucket: str | None = None

    data_quality_score: int = 0
    contactability_score: int = 0  # gate, not main
    content_format_score: int = 0
    content_format_status: str = "unknown"
    commerce_signal_score: int = 0
    repeat_discovery_score: int = 0
    repeat_video_count: int = 0
    repeat_keyword_count: int = 0
    repeat_same_keyword_extra_video_count: int = 0
    repeat_commerce_observation_count: int = 0
    repeat_tag_boosts: dict[str, int] = field(default_factory=dict)
    commercial_value_score: int = 0
    follower_scale_score: int = 0
    audience_fit_score: int = 0  # bonus, capped at 10

    recommendation_score: int = 0  # composite priority/recommendation score

    # Evidence buckets
    evidence: dict[str, list[dict]] = field(default_factory=dict)
    evidence_strength: str = "weak"  # weak | medium | strong
    fit_evidence_sources: list[str] = field(default_factory=list)

    # Audience tags + email kind (used downstream by tag engine)
    audience_tags: list[str] = field(default_factory=list)
    email_kind: str = "missing"
    email_is_suspect: bool = False
    contact_types: list[str] = field(default_factory=list)

    # Flags surfaced from scoring (re-used by recommendation_engine)
    feminine_search_only_match: bool = False
    has_email: bool = False
    has_contact: bool = False


def compute_score(record: dict) -> ScoreResult:
    bio = record.get("bio") or ""
    title = record.get("source_video_title") or ""
    desc = record.get("source_video_description") or ""
    hashtags_blob = " ".join(record.get("hashtags") or [])
    search_keyword = record.get("search_keyword") or ""
    repeat = _repeat_discovery(record.get("repeat_discovery"))

    strong_sources = {
        "bio": bio,
        "source_video_title": title,
        "source_video_description": desc,
    }
    medium_sources = {
        "hashtags": hashtags_blob,
        "external_links_text": " ".join(record.get("external_links") or []),
    }
    all_sources = {**strong_sources, **medium_sources, "search_keyword": search_keyword}

    # --- feminine fit ---
    strong_hits = find_keyword_hits(FEMININE_STRONG_KEYWORDS, strong_sources)
    medium_hits = find_keyword_hits(FEMININE_STRONG_KEYWORDS, medium_sources)
    adjacent_hits = find_keyword_hits(FEMININE_ADJACENT_KEYWORDS, strong_sources)
    fmt_in_fem = find_keyword_hits(FEMININE_FORMAT_KEYWORDS, strong_sources)

    strong_total = cap(_sum_unique(strong_hits), FEMININE_STRONG_CAP)
    # Medium evidence adds at half points, capped inside the strong cap.
    medium_total = cap(_sum_unique(medium_hits) // 2, max(0, FEMININE_STRONG_CAP - strong_total))
    adjacent_total = cap(_sum_unique(adjacent_hits), FEMININE_ADJACENT_CAP)
    format_total = cap(_sum_unique(fmt_in_fem), FEMININE_FORMAT_CAP)

    sk_norm = normalize(search_keyword)
    fem_search_bonus = 0
    fem_search_used = ""
    for phrase in FEMININE_SEARCH_KEYWORDS:
        if phrase in sk_norm:
            fem_search_bonus = FEMININE_SEARCH_KEYWORD_BONUS
            fem_search_used = phrase
            break

    feminine_care_fit = cap(
        strong_total + medium_total + adjacent_total + format_total + fem_search_bonus
        + repeat["tag_boosts"].get("feminine_care", 0),
        100,
    )

    has_strong_evidence = bool(strong_hits or adjacent_hits)
    has_any_real_evidence = has_strong_evidence or bool(medium_hits)
    feminine_search_only_match = bool(fem_search_bonus) and not has_any_real_evidence

    # Evidence sources used
    fit_evidence_sources: list[str] = []
    if strong_hits or adjacent_hits or fmt_in_fem:
        fit_evidence_sources.extend(sorted({h.evidence_source for h in (strong_hits + adjacent_hits + fmt_in_fem)}))
    if medium_hits:
        fit_evidence_sources.extend(sorted({h.evidence_source for h in medium_hits}))
    if fem_search_bonus and not has_any_real_evidence:
        fit_evidence_sources.append("search_keyword")
    fit_evidence_sources = list(dict.fromkeys(fit_evidence_sources))

    # Evidence strength label
    if has_strong_evidence:
        evidence_strength = "strong"
    elif medium_hits:
        evidence_strength = "medium"
    else:
        evidence_strength = "weak"

    # --- other category fits (flat 20 per unique keyword, cap 100) ---
    pet_hits = find_simple_keywords(PET_CARE_KEYWORDS, strong_sources)
    home_hits = find_simple_keywords(HOME_CARE_KEYWORDS, strong_sources)
    adult_hits = find_simple_keywords(ADULT_CARE_KEYWORDS, strong_sources)
    mom_hits = find_simple_keywords(MOM_BABY_KEYWORDS, strong_sources)
    mask_hits = find_simple_keywords(HEALTH_MASK_KEYWORDS, strong_sources)

    pet_care_fit = cap(_unique_count(pet_hits) * OTHER_CATEGORY_HIT_POINTS + repeat["tag_boosts"].get("pet_care", 0), 100)
    home_care_fit = cap(_unique_count(home_hits) * OTHER_CATEGORY_HIT_POINTS + repeat["tag_boosts"].get("home_care", 0), 100)
    adult_care_fit = cap(_unique_count(adult_hits) * OTHER_CATEGORY_HIT_POINTS + repeat["tag_boosts"].get("adult_care", 0), 100)
    mom_baby_fit = cap(_unique_count(mom_hits) * OTHER_CATEGORY_HIT_POINTS + repeat["tag_boosts"].get("mom_baby", 0), 100)
    health_mask_fit = cap(_unique_count(mask_hits) * OTHER_CATEGORY_HIT_POINTS + repeat["tag_boosts"].get("health_mask", 0), 100)

    fits = {
        "feminine_care": feminine_care_fit,
        "pet_care": pet_care_fit,
        "home_care": home_care_fit,
        "adult_care": adult_care_fit,
        "mom_baby": mom_baby_fit,
        "health_mask": health_mask_fit,
    }
    sortable = dict(fits)
    if feminine_search_only_match:
        # Don't let search-keyword-only feminine win the primary race —
        # recommendation_engine will still see feminine_care_fit but
        # primary_product_category becomes general_lifestyle.
        sortable["feminine_care"] = 0

    primary_cat, primary_score = max(sortable.items(), key=lambda kv: kv[1])
    if primary_score < 40:
        primary_cat = "general_lifestyle"
        primary_score = 0

    # --- granular feminine bucket suggestion ---
    suggested_feminine_bucket: str | None = None
    if primary_cat == "feminine_care":
        text_blob = " ".join(normalize(s) for s in strong_sources.values())
        suggested_feminine_bucket = pick_feminine_product_bucket(text_blob)

    # --- content format score ---
    fmt_hits = find_keyword_hits(CONTENT_FORMAT_KEYWORDS, strong_sources)
    content_format_score = cap(_sum_unique(fmt_hits), 100)
    if content_format_score >= 30:
        content_format_status = "match"
    elif content_format_score > 0:
        content_format_status = "partial_match"
    elif bio or title or desc:
        # We saw text but no format keywords — that's not_match, not unknown.
        content_format_status = "not_match"
    else:
        content_format_status = "unknown"

    # --- commerce signal score ---
    commerce_sources = {**strong_sources, **medium_sources}
    commerce_hits = find_keyword_hits(COMMERCE_SIGNAL_KEYWORDS, commerce_sources)
    commerce_signal_score = cap(_sum_unique(commerce_hits), 100)

    # --- commercial value score ---
    followers = int(record.get("followers_count") or 0)
    likes = int(record.get("likes_count") or 0)
    fs = follower_scale_score(followers)
    commercial = fs
    if followers > 0 and likes and (likes / max(followers, 1)) > 50:
        commercial += 10
    bio_norm = normalize(bio)
    if any(w in bio_norm for w in ("collab", "pr ", "sample", "business email", "ugc")):
        commercial += 10
    if any(h.tag_code in {"ugc_creator", "review_style", "deal_finds_style", "unboxing_style"} for h in fmt_hits):
        commercial += 10
    commercial += min(30, commerce_signal_score // 2)
    email_info = classify_email(record.get("email"))
    contact_types = contact_types_for(record.get("email"), bio, record.get("external_links"))
    has_profile_contact = has_contact_method(record.get("email"), bio, record.get("external_links"))
    if email_info["kind"] == "agency":
        commercial -= 10
    if followers > 1_000_000 and primary_cat == "general_lifestyle":
        commercial -= 20
    if followers > 3_000_000:
        commercial -= 25
    commercial += min(15, repeat["score"] // 5)
    commercial_value_score = max(0, min(100, commercial))

    # --- data quality ---
    dq = 0
    if record.get("handle"): dq += 25
    if record.get("profile_url"): dq += 20
    if bio: dq += 20
    if followers > 0: dq += 15
    if likes: dq += 10
    if record.get("source_video_url") and "/video/" in (record.get("source_video_url") or ""):
        dq += 10
    data_quality_score = min(dq, 100)

    # --- contactability — profile-description contact gate ---
    if email_info["kind"] == "missing":
        contactability_score = 80 if has_profile_contact else 0
    elif email_info["is_suspect"] or email_info["kind"] == "suspect":
        contactability_score = 50
    else:
        contactability_score = 100

    # --- audience bonus (cap 10) ---
    audience_tags: list[str] = []
    audience_bonus = 0
    big_norm = " ".join(normalize(s) for s in strong_sources.values())
    for tag, pts, kws in AUDIENCE_RULES:
        if any(phrase_present(k, big_norm) for k in kws):
            if tag in audience_tags:
                continue
            audience_tags.append(tag)
            audience_bonus += pts
    audience_bonus = cap(audience_bonus, AUDIENCE_BONUS_CAP)

    # --- recommendation_score (spec section 8) ---
    raw = (
        primary_score * 0.35
        + commercial_value_score * 0.30
        + content_format_score * 0.20
        + fs * 0.05
        + data_quality_score * 0.05
        + audience_bonus * 0.05
        + repeat["score"] * 0.10
    )
    if contactability_score > 0:
        raw += 8
    if contactability_score > 0 and data_quality_score >= 50 and primary_score >= 20:
        raw += 4
    recommendation_score = max(0, min(100, int(round(raw))))

    return ScoreResult(
        feminine_care_fit=feminine_care_fit,
        pet_care_fit=pet_care_fit,
        home_care_fit=home_care_fit,
        adult_care_fit=adult_care_fit,
        mom_baby_fit=mom_baby_fit,
        health_mask_fit=health_mask_fit,
        primary_product_category=primary_cat,
        primary_product_fit_score=primary_score,
        suggested_feminine_bucket=suggested_feminine_bucket,
        data_quality_score=data_quality_score,
        contactability_score=contactability_score,
        content_format_score=content_format_score,
        content_format_status=content_format_status,
        commerce_signal_score=commerce_signal_score,
        repeat_discovery_score=repeat["score"],
        repeat_video_count=repeat["unique_video_count"],
        repeat_keyword_count=repeat["unique_keyword_count"],
        repeat_same_keyword_extra_video_count=repeat["same_keyword_extra_video_count"],
        repeat_commerce_observation_count=repeat["commerce_observation_count"],
        repeat_tag_boosts=repeat["tag_boosts"],
        commercial_value_score=commercial_value_score,
        follower_scale_score=fs,
        audience_fit_score=audience_bonus,
        recommendation_score=recommendation_score,
        evidence={
            "feminine_strong": [_h(h) for h in strong_hits],
            "feminine_medium": [_h(h) for h in medium_hits],
            "feminine_adjacent": [_h(h) for h in adjacent_hits],
            "feminine_format": [_h(h) for h in fmt_in_fem],
            "feminine_search_keyword": ([{"keyword": fem_search_used, "points": fem_search_bonus}] if fem_search_bonus else []),
            "pet_care": [_h(h) for h in pet_hits],
            "home_care": [_h(h) for h in home_hits],
            "adult_care": [_h(h) for h in adult_hits],
            "mom_baby": [_h(h) for h in mom_hits],
            "health_mask": [_h(h) for h in mask_hits],
            "content_format": [_h(h) for h in fmt_hits],
            "commerce_signal": [_h(h) for h in commerce_hits],
            "repeat_discovery": _repeat_evidence(repeat),
        },
        evidence_strength=evidence_strength,
        fit_evidence_sources=fit_evidence_sources,
        audience_tags=audience_tags,
        email_kind=email_info["kind"],
        email_is_suspect=bool(email_info["is_suspect"]),
        contact_types=contact_types,
        feminine_search_only_match=feminine_search_only_match,
        has_email=email_info["kind"] != "missing" and not email_info["is_suspect"],
        has_contact=has_profile_contact,
    )


def _h(hit: KeywordHit) -> dict:
    return {
        "keyword": hit.keyword,
        "points": hit.points,
        "tag_code": hit.tag_code,
        "evidence_source": hit.evidence_source,
        "evidence_snippet": hit.evidence_snippet,
    }


def _sum_unique(hits: list[KeywordHit]) -> int:
    seen: dict[str, int] = {}
    for h in hits:
        if h.keyword not in seen or h.points > seen[h.keyword]:
            seen[h.keyword] = h.points
    return sum(seen.values())


def _unique_count(hits: list[KeywordHit]) -> int:
    return len({h.keyword for h in hits})


def _repeat_discovery(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    unique_keyword_count = _as_int(value.get("unique_keyword_count"))
    unique_video_count = _as_int(value.get("unique_video_count"))
    same_keyword_extra_video_count = _as_int(value.get("same_keyword_extra_video_count"))
    max_tag_support_count = _as_int(value.get("max_tag_support_count"))
    commerce_observation_count = _as_int(value.get("commerce_observation_count"))

    tag_boosts: dict[str, int] = {}
    raw_boosts = value.get("tag_boosts") or {}
    if isinstance(raw_boosts, dict):
        for key, raw in raw_boosts.items():
            pts = min(20, max(0, _as_int(raw)))
            if pts:
                tag_boosts[str(key)] = pts

    score = cap(
        min(18, same_keyword_extra_video_count * 6)
        + min(30, max(0, unique_keyword_count - 1) * 12)
        + min(20, max(0, max_tag_support_count - 1) * 5)
        + min(20, max(0, commerce_observation_count - 1) * 10),
        100,
    )
    return {
        "score": score,
        "unique_keyword_count": unique_keyword_count,
        "unique_video_count": unique_video_count,
        "same_keyword_extra_video_count": same_keyword_extra_video_count,
        "commerce_observation_count": commerce_observation_count,
        "tag_boosts": tag_boosts,
    }


def _repeat_evidence(repeat: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if repeat["score"]:
        rows.append({"keyword": "repeat_discovery_score", "points": repeat["score"]})
    if repeat["same_keyword_extra_video_count"]:
        rows.append({"keyword": "same_keyword_multi_video", "points": min(18, repeat["same_keyword_extra_video_count"] * 6)})
    if repeat["unique_keyword_count"] > 1:
        rows.append({"keyword": "multi_keyword_discovery", "points": min(30, (repeat["unique_keyword_count"] - 1) * 12)})
    for tag, pts in repeat["tag_boosts"].items():
        rows.append({"keyword": f"repeat_{tag}_boost", "points": pts, "tag_code": tag})
    if repeat["commerce_observation_count"] > 1:
        rows.append({"keyword": "repeat_commerce_signal", "points": min(20, (repeat["commerce_observation_count"] - 1) * 10)})
    return rows


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
