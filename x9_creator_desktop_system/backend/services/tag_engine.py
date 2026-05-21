"""tag_engine.py — emits risk + positive tags from a ScoreResult."""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models.creator import Creator
from ..models.creator_tag import CreatorTag
from ..utils.id_utils import new_id
from ..utils.json_utils import dumps_json, loads_json_list
from .scoring_engine import ScoreResult


RISK = "risk"
POSITIVE = "positive"
PRODUCT = "product_category"
FORMAT = "content_format"
COLLAB = "collaboration"


def emit_tags(creator: Creator, score: ScoreResult) -> tuple[list[str], list[str]]:
    """Pure compute — return (risk_tags, positive_tags) lists for the
    creator. The DB-bound helper `apply_tags` writes them.

    Returns separately since they're stored in JSON fields on the
    creator row AND as individual rows in creator_tags.
    """
    risk: list[str] = []
    positive: list[str] = []

    f = creator.followers_count or 0

    # ----- risk tags -----
    if score.feminine_search_only_match:
        risk.append("search_keyword_only_match")
        if score.commerce_signal_score >= 70 or score.repeat_discovery_score >= 60:
            risk.append("product_fit_uncertain_but_commerce_strong")
    if score.evidence_strength == "weak" and score.primary_product_fit_score < 40:
        risk.append("weak_category_evidence")
    if not score.has_contact:
        risk.append("missing_email")
    if score.content_format_status == "unknown":
        risk.append("unknown_content_format")
    if score.primary_product_fit_score < 40 and not score.feminine_search_only_match:
        risk.append("low_product_fit")
    if f >= 500_000 and score.primary_product_fit_score < 40:
        risk.append("macro_low_fit")
    fits_above_40 = sum(1 for v in (
        score.feminine_care_fit, score.pet_care_fit, score.home_care_fit,
        score.adult_care_fit, score.mom_baby_fit, score.health_mask_fit
    ) if v >= 40)
    if fits_above_40 >= 2:
        risk.append("conflicting_category_signals")

    # ----- positive tags -----
    if score.has_email:
        positive.append("has_email")
    elif score.has_contact:
        positive.append("has_alt_contact")
    if f >= 500_000:
        positive.append("high_followers")
    elif f >= 50_000:
        positive.append("medium_followers")
    elif f > 0:
        positive.append("micro_creator")
    if score.feminine_care_fit >= 70:
        positive.append("strong_feminine_care_fit")
    elif score.feminine_care_fit >= 40:
        positive.append("medium_feminine_care_fit")
    if score.commercial_value_score >= 70:
        positive.append("high_commercial_value")
    if score.commerce_signal_score >= 70:
        positive.append("strong_commerce_signal")
    if score.commerce_signal_score >= 60 and score.primary_product_fit_score < 60 and score.has_contact:
        positive.append("commerce_test_candidate")
    if 5_000 <= f <= 100_000 and score.commercial_value_score >= 70:
        positive.append("sample_collab_candidate")
    if score.commercial_value_score >= 70 and score.primary_product_fit_score < 60:
        positive.append("affiliate_candidate")
    if score.commerce_signal_score >= 60 and score.primary_product_fit_score < 60:
        positive.append("affiliate_candidate")
    if score.repeat_discovery_score >= 25:
        positive.append("repeat_target_tag_signal")
    if score.repeat_same_keyword_extra_video_count > 0:
        positive.append("same_keyword_multi_video")
    if score.repeat_keyword_count > 1:
        positive.append("multi_keyword_discovery")
    if score.repeat_commerce_observation_count > 1:
        positive.append("repeat_commerce_signal")
    for category, pts in score.repeat_tag_boosts.items():
        if pts > 0:
            positive.append(f"repeat_{category}_signal")
    if f >= 500_000:
        positive.append("brand_awareness_candidate")

    # dedup preserving order
    return list(dict.fromkeys(risk)), list(dict.fromkeys(positive))


def apply_tags(db: Session, creator: Creator, score: ScoreResult) -> int:
    """Replace this creator's tags with the v3 set; also write JSON
    summaries onto the Creator row for fast filtering."""
    risk, positive = emit_tags(creator, score)

    db.execute(delete(CreatorTag).where(CreatorTag.creator_id == creator.id))

    rows: list[CreatorTag] = []
    seen: set[str] = set()
    for code in risk:
        if code in seen: continue
        seen.add(code)
        rows.append(CreatorTag(id=new_id("ctag"), creator_id=creator.id, tag_code=code,
                               department_code=creator.department_code,
                               tag_type=RISK, source="rule_engine", confidence=1.0))
    for code in positive:
        if code in seen: continue
        seen.add(code)
        rows.append(CreatorTag(id=new_id("ctag"), creator_id=creator.id, tag_code=code,
                               department_code=creator.department_code,
                               tag_type=POSITIVE, source="rule_engine", confidence=0.9))

    # Also surface the primary product category as its own tag.
    if score.primary_product_category and score.primary_product_category != "general_lifestyle":
        cat = score.primary_product_category
        if cat not in seen:
            seen.add(cat)
            rows.append(CreatorTag(id=new_id("ctag"), creator_id=creator.id, tag_code=cat,
                                   department_code=creator.department_code,
                                   tag_type=PRODUCT, source="rule_engine", confidence=0.9))

    for r in rows:
        db.add(r)

    creator.risk_tags_json = dumps_json(risk)
    creator.positive_tags_json = dumps_json(positive)
    return len(rows)


def find_creators_by_tags(
    db: Session,
    tag_codes: list[str],
    require_all: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[Creator]:
    if not tag_codes:
        return []
    base = (
        select(Creator)
        .join(CreatorTag, CreatorTag.creator_id == Creator.id)
        .where(CreatorTag.tag_code.in_(tag_codes))
        .group_by(Creator.id)
        .order_by(Creator.recommendation_score.desc())
        .offset(offset).limit(limit)
    )
    if require_all:
        base = base.having(func.count(func.distinct(CreatorTag.tag_code)) >= len(set(tag_codes)))
    return list(db.scalars(base).all())
