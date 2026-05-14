"""pipeline.py — full creator processing chain.

Score → tag → recommend in one pass per creator.
This is what `POST /api/local/process/run-full-pipeline` calls and
what tests rely on.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models.creator import Creator
from ..models.creator_recommendation import CreatorRecommendation
from ..models.raw_observation import RawObservation
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json, loads_json_list
from ..utils.keyword_rules_v3 import (
    ADULT_CARE_KEYWORDS,
    COMMERCE_SIGNAL_KEYWORDS,
    FEMININE_ADJACENT_KEYWORDS,
    FEMININE_FORMAT_KEYWORDS,
    FEMININE_SEARCH_KEYWORDS,
    FEMININE_STRONG_KEYWORDS,
    HEALTH_MASK_KEYWORDS,
    HOME_CARE_KEYWORDS,
    MOM_BABY_KEYWORDS,
    PET_CARE_KEYWORDS,
    find_keyword_hits,
    find_simple_keywords,
    normalize,
    phrase_present,
)
from .recommendation_engine import decide
from .review_task_service import open_task_if_needed
from .departments import department_where
from .scoring_engine import compute_score
from .tag_engine import apply_tags


def run_for_creator(db: Session, creator: Creator, repeat_discovery: dict[str, Any] | None = None) -> dict:
    """Idempotent single-creator pipeline."""
    if repeat_discovery is None:
        repeat_discovery = _repeat_discovery_for_creators(db, [creator]).get(creator.id, {})
    record = _creator_to_dict(creator, repeat_discovery)
    score = compute_score(record)

    # Persist scores
    creator.feminine_care_fit = score.feminine_care_fit
    creator.pet_care_fit = score.pet_care_fit
    creator.home_care_fit = score.home_care_fit
    creator.adult_care_fit = score.adult_care_fit
    creator.mom_baby_fit = score.mom_baby_fit
    creator.health_mask_fit = score.health_mask_fit
    creator.primary_product_category = score.primary_product_category
    creator.primary_product_fit_score = score.primary_product_fit_score
    creator.data_quality_score = score.data_quality_score
    creator.contactability_score = score.contactability_score
    creator.content_format_score = score.content_format_score
    creator.content_format_status = score.content_format_status
    creator.commercial_value_score = score.commercial_value_score
    creator.follower_scale_score = score.follower_scale_score
    creator.audience_fit_score = score.audience_fit_score
    creator.recommendation_score = score.recommendation_score
    creator.priority_score = score.recommendation_score  # alias for older queries
    creator.fit_evidence_source_json = dumps_json(score.fit_evidence_sources)
    creator.matched_keywords_json = dumps_json([h["keyword"] for hits in score.evidence.values() for h in hits if isinstance(h, dict)])
    creator.evidence_text_json = dumps_json(score.evidence)
    creator.evidence_strength = score.evidence_strength
    from ..utils.keyword_rules_v3 import fit_level_for
    creator.fit_level = fit_level_for(score.primary_product_fit_score)
    creator.score_version = settings.score_version
    creator.scored_at = datetime.now(timezone.utc)

    # Tags (writes risk_tags_json + positive_tags_json on creator)
    apply_tags(db, creator, score)
    creator.tag_version = settings.tag_version
    creator.tagged_at = datetime.now(timezone.utc)

    # Recommendation decision
    decision = decide(
        score,
        followers=creator.followers_count or 0,
        has_email=bool(score.has_email),
        has_contact=bool(score.has_contact),
    )
    creator.recommendation_status = decision.recommendation_status
    creator.recommended_product_type = decision.recommended_product_type
    creator.recommended_collab_type = decision.recommended_collab_type
    creator.outreach_priority = decision.outreach_priority
    creator.priority_level = decision.outreach_priority  # alias
    creator.queue_type = decision.queue_type
    creator.recommendation_reason = decision.recommendation_reason
    creator.next_action = decision.next_action
    creator.risk_summary = decision.risk_summary
    creator.review_required = 1 if decision.review_required else 0
    if decision.review_required:
        creator.review_status = "pending"
    elif creator.review_status not in ("approved", "rejected", "hold"):
        creator.review_status = None
    creator.rec_version = settings.rec_version
    creator.recommended_at = datetime.now(timezone.utc)

    # Append a history row (so we can audit recommendation drift)
    db.add(CreatorRecommendation(
        id=new_id("rec"),
        department_code=creator.department_code,
        creator_id=creator.id,
        recommendation_status=decision.recommendation_status,
        recommended_product_type=decision.recommended_product_type,
        recommended_collab_type=decision.recommended_collab_type,
        outreach_priority=decision.outreach_priority,
        recommendation_score=score.recommendation_score,
        recommendation_reason=decision.recommendation_reason,
        risk_summary=decision.risk_summary,
        next_action=decision.next_action,
        rec_version=settings.rec_version,
    ))

    # No new manual-review tasks are created in the multi-user BD flow.
    # The helper is still called so old pending tasks close automatically
    # when a creator is re-routed by the current rules.
    open_task_if_needed(db, creator)
    return {"creator_id": creator.id, "queue": decision.queue_type, "status": decision.recommendation_status}


def run_full_pipeline(
    db: Session,
    creator_id: str | None = None,
    limit: int = 5000,
    department_code: str | None = None,
) -> dict:
    q = select(Creator)
    if creator_id:
        q = q.where(Creator.id == creator_id)
    where_department = department_where(Creator, department_code)
    if where_department is not None:
        q = q.where(where_department)
    q = q.limit(limit)
    creators = list(db.scalars(q).all())
    repeat_by_creator = _repeat_discovery_for_creators(db, creators)
    counts: dict[str, int] = {}
    for c in creators:
        out = run_for_creator(db, c, repeat_by_creator.get(c.id, {}))
        counts[out["queue"]] = counts.get(out["queue"], 0) + 1
    db.commit()
    return {"processed": len(creators), "queues": counts}


def _creator_to_dict(creator: Creator, repeat_discovery: dict[str, Any] | None = None) -> dict:
    return {
        "platform": creator.platform,
        "search_keyword": creator.search_keyword,
        "bio": creator.bio,
        "source_video_url": creator.source_video_url,
        "source_video_title": creator.source_video_title,
        "source_video_description": creator.source_video_description,
        "handle": creator.handle,
        "display_name": creator.display_name,
        "profile_url": creator.profile_url,
        "followers_count": creator.followers_count,
        "likes_count": None,
        "email": creator.email,
        "external_links": loads_json_list(creator.external_links_json),
        "hashtags": [],
        "repeat_discovery": repeat_discovery or {},
    }


def _repeat_discovery_for_creators(db: Session, creators: list[Creator]) -> dict[str, dict[str, Any]]:
    if not creators:
        return {}

    creator_keys = {
        ((c.platform or "tiktok").lower(), _norm_handle(c.handle)): c.id
        for c in creators
        if c.handle
    }
    if not creator_keys:
        return {}

    states = {c.id: _new_repeat_state() for c in creators}
    platforms = sorted({p for p, _ in creator_keys})
    rows = list(db.scalars(select(RawObservation).where(RawObservation.platform.in_(platforms))).all())

    for obs in rows:
        payload = _load_payload(obs.raw_json)
        if not payload:
            continue
        creator_data = payload.get("creator") or {}
        cid = creator_keys.get(((payload.get("platform") or obs.platform or "tiktok").lower(), _norm_handle(creator_data.get("handle"))))
        if not cid:
            continue
        _add_repeat_observation(states[cid], payload, obs)

    return {cid: _finalize_repeat_state(state) for cid, state in states.items()}


def _new_repeat_state() -> dict[str, Any]:
    return {
        "observation_count": 0,
        "keywords": set(),
        "videos": set(),
        "seen_pairs": set(),
        "keyword_to_videos": defaultdict(set),
        "tag_supports": defaultdict(set),
        "commerce_supports": set(),
    }


def _add_repeat_observation(state: dict[str, Any], payload: dict[str, Any], obs: RawObservation) -> None:
    keyword_raw = payload.get("search_keyword") or obs.search_keyword or ""
    keyword_norm = normalize(keyword_raw)
    source_video = payload.get("source_video") or {}
    video_url = (source_video.get("video_url") or "").strip()
    video_key = video_url if "/video/" in video_url else ""
    pair_key = (keyword_norm, video_key)
    if pair_key in state["seen_pairs"]:
        return
    state["seen_pairs"].add(pair_key)
    state["observation_count"] += 1

    if keyword_norm:
        state["keywords"].add(keyword_norm)
    if video_key:
        state["videos"].add(video_key)
        if keyword_norm:
            state["keyword_to_videos"][keyword_norm].add(video_key)

    support_key = video_key or (f"keyword:{keyword_norm}" if keyword_norm else f"obs:{obs.content_hash}")
    sources = {
        "search_keyword": keyword_raw,
        "bio": (payload.get("creator") or {}).get("bio") or "",
        "source_video_title": source_video.get("title") or "",
        "source_video_description": source_video.get("description") or "",
    }
    for category in _categories_for_sources(sources):
        state["tag_supports"][category].add(support_key)
    if find_keyword_hits(COMMERCE_SIGNAL_KEYWORDS, sources):
        state["commerce_supports"].add(support_key)


def _categories_for_sources(sources: dict[str, str]) -> set[str]:
    categories: set[str] = set()
    keyword_norm = normalize(sources.get("search_keyword"))
    if any(phrase_present(phrase, keyword_norm) for phrase in FEMININE_SEARCH_KEYWORDS):
        categories.add("feminine_care")
    if find_keyword_hits(FEMININE_STRONG_KEYWORDS + FEMININE_ADJACENT_KEYWORDS + FEMININE_FORMAT_KEYWORDS, sources):
        categories.add("feminine_care")
    for category, keywords in (
        ("pet_care", PET_CARE_KEYWORDS),
        ("home_care", HOME_CARE_KEYWORDS),
        ("adult_care", ADULT_CARE_KEYWORDS),
        ("mom_baby", MOM_BABY_KEYWORDS),
        ("health_mask", HEALTH_MASK_KEYWORDS),
    ):
        if find_simple_keywords(keywords, sources):
            categories.add(category)
    return categories


def _finalize_repeat_state(state: dict[str, Any]) -> dict[str, Any]:
    tag_support_counts = {tag: len(supports) for tag, supports in state["tag_supports"].items()}
    tag_boosts = {
        tag: min(20, max(0, count - 1) * 5)
        for tag, count in tag_support_counts.items()
        if count > 1
    }
    same_keyword_extra_video_count = sum(max(0, len(videos) - 1) for videos in state["keyword_to_videos"].values())
    return {
        "observation_count": state["observation_count"],
        "unique_keyword_count": len(state["keywords"]),
        "unique_video_count": len(state["videos"]),
        "same_keyword_extra_video_count": same_keyword_extra_video_count,
        "commerce_observation_count": len(state["commerce_supports"]),
        "tag_support_counts": tag_support_counts,
        "tag_boosts": tag_boosts,
        "max_tag_support_count": max(tag_support_counts.values(), default=0),
    }


def _load_payload(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _norm_handle(value: str | None) -> str:
    return (value or "").strip().lower().lstrip("@")
