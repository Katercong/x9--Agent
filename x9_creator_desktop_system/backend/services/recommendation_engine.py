"""recommendation_engine.py — turns a ScoreResult into a business decision.

Owns spec sections 7–13: queue routing, product type, collab type,
priority, status, recommendation_reason, next_action.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scoring_engine import ScoreResult


# Queue codes
QUEUE_FEMININE_CONVERSION = "feminine_conversion_queue"
QUEUE_FEMININE_WARM = "feminine_warm_lead_queue"
QUEUE_SAMPLE = "sample_collab_test_queue"
QUEUE_AFFILIATE = "affiliate_test_queue"
QUEUE_MACRO = "macro_brand_awareness_queue"
QUEUE_MANUAL_REVIEW = "manual_review_queue"
QUEUE_LOW_CONFIDENCE_HOLD = "low_confidence_hold"
QUEUE_GENERAL_HOLD = "general_lifestyle_hold"
QUEUE_NOT_RECOMMENDED = "not_recommended_queue"
QUEUE_NO_CONTACT = "no_contact_info_queue"

# Recommendation status codes
STATUS_RECOMMENDED = "recommended"
STATUS_RECOMMENDED_AFTER_REVIEW = "recommended_after_review"
STATUS_LOW_COST_TEST = "low_cost_test"
STATUS_AFFILIATE_TEST = "affiliate_test"
STATUS_BRAND_AWARENESS_ONLY = "brand_awareness_only"
STATUS_MANUAL_REVIEW = "manual_review_before_outreach"
STATUS_HOLD = "hold"
STATUS_NOT_RECOMMENDED = "not_recommended_now"
STATUS_NO_CONTACT = "no_contact_info"

# Collab types
COLLAB_SAMPLE = "sample_collab"
COLLAB_GIFTED = "gifted_review"
COLLAB_AFFILIATE = "affiliate_collab"
COLLAB_PAID = "paid_test_collab"
COLLAB_BRAND_AWARENESS = "brand_awareness_collab"
COLLAB_DO_NOT_CONTACT = "do_not_contact_now"

# Outreach priority levels
P1, P2, P3, P4 = "P1", "P2", "P3", "P4"


@dataclass
class Decision:
    recommendation_status: str
    recommended_product_type: str | None
    recommended_collab_type: str
    outreach_priority: str
    queue_type: str
    recommendation_reason: str
    next_action: str
    risk_summary: str
    review_required: bool


def decide(
    score: ScoreResult,
    *,
    followers: int,
    has_email: bool | None = None,
    has_contact: bool | None = None,
) -> Decision:
    """Apply the spec rules in priority order. The FIRST rule that
    matches wins; that means hard gates (no contact, search-only match)
    are checked before any recommendation logic."""
    if has_contact is None:
        has_contact = bool(has_email)

    # --- Hard gate 1: no usable contact -> no_contact_info_queue ---
    if not has_contact:
        return Decision(
            recommendation_status=STATUS_NO_CONTACT,
            recommended_product_type=score.primary_product_category if score.primary_product_fit_score >= 40 else None,
            recommended_collab_type=COLLAB_DO_NOT_CONTACT,
            outreach_priority=P4,
            queue_type=QUEUE_NO_CONTACT,
            recommendation_reason=(
                "No usable contact channel is visible in the creator profile description. "
                "Outreach is blocked until email, WhatsApp, or another direct contact method is confirmed."
            ),
            next_action="Check the creator description again for email, WhatsApp, or another direct contact method.",
            risk_summary="missing_contact",
            review_required=False,
        )

    fcf = score.feminine_care_fit
    primary_cat = score.primary_product_category
    primary_score = score.primary_product_fit_score
    cv = score.commercial_value_score
    cs = score.commerce_signal_score
    rd = score.repeat_discovery_score
    dq = score.data_quality_score

    # --- Hard gate 2 with commerce override ---
    # Search-keyword-only creators should not enter paid conversion, but
    # strong live-shopping / affiliate / review signals are worth a
    # low-cost test before ordinary lifestyle accounts.
    if score.feminine_search_only_match:
        if (cs >= 85 or (rd >= 75 and cs >= 60)) and followers <= 100_000:
            return Decision(
                recommendation_status=STATUS_LOW_COST_TEST,
                recommended_product_type=None,
                recommended_collab_type=COLLAB_GIFTED,
                outreach_priority=P3,
                queue_type=QUEUE_SAMPLE,
                recommendation_reason=(
                    "Product fit is not confirmed beyond the search keyword, but commerce signals are very strong "
                    f"(commerce={cs}, repeat={rd}, cv={cv}). Treat this as a low-cost gifted review test, not paid conversion."
                ),
                next_action="Send a small gifted sample and require one organic review; stop if product fit is not confirmed.",
                risk_summary="search_keyword_only_match; product_fit_uncertain_but_commerce_strong",
                review_required=False,
            )
        if cs >= 70 or rd >= 60:
            return Decision(
                recommendation_status=STATUS_AFFILIATE_TEST,
                recommended_product_type=None,
                recommended_collab_type=COLLAB_AFFILIATE,
                outreach_priority=P3,
                queue_type=QUEUE_AFFILIATE,
                recommendation_reason=(
                    "Feminine-care fit comes only from the search keyword, but repeated discovery or commerce signals are strong "
                    f"(repeat={rd}, commerce={cs}, cv={cv}). Commission-only outreach is safer than manual hold."
                ),
                next_action="Offer an affiliate / commission-only collaboration and verify fit before sending budget.",
                risk_summary="search_keyword_only_match; product_fit_uncertain_but_commerce_strong",
                review_required=False,
            )
        return Decision(
            recommendation_status=STATUS_HOLD,
            recommended_product_type=None,
            recommended_collab_type=COLLAB_DO_NOT_CONTACT,
            outreach_priority=P4,
            queue_type=QUEUE_LOW_CONFIDENCE_HOLD,
            recommendation_reason=(
                "Valid email present, but feminine-care match comes only from the search keyword. "
                "Bio, video title and video description do not contain real feminine-care evidence. "
                "The lead is held automatically until stronger product-fit evidence appears."
            ),
            next_action="Do not contact now. Re-score after collecting stronger bio or video evidence.",
            risk_summary="search_keyword_only_match; low_confidence_hold",
            review_required=False,
        )

    # --- 1. feminine_conversion_queue ---
    if (
        primary_cat == "feminine_care"
        and fcf >= 70
        and "search_keyword" not in (score.fit_evidence_sources or [])
        and cv >= 50
    ):
        product_type = score.suggested_feminine_bucket or "period_care_pad"
        if score.recommendation_score >= 70:
            collab = COLLAB_PAID
            priority = P1 if score.recommendation_score >= 80 else P2
        else:
            collab = COLLAB_SAMPLE
            priority = P2
        return Decision(
            recommendation_status=STATUS_RECOMMENDED,
            recommended_product_type=product_type,
            recommended_collab_type=collab,
            outreach_priority=priority,
            queue_type=QUEUE_FEMININE_CONVERSION,
            recommendation_reason=(
                f"Strong feminine-care evidence in {', '.join(score.fit_evidence_sources)} (fit={fcf}). "
                f"Commercial value {cv} and content format score {score.content_format_score} support paid collaboration. "
                f"Suggested SKU bucket: {product_type}."
            ),
            next_action="Send paid collaboration brief or branded sample box and confirm shipping.",
            risk_summary="",
            review_required=False,
        )

    # --- 2. feminine_warm_lead_queue ---
    if (
        primary_cat == "feminine_care"
        and 40 <= fcf <= 69
        and dq >= 70
        and cv >= 50
    ):
        return Decision(
            recommendation_status=STATUS_LOW_COST_TEST,
            recommended_product_type=score.suggested_feminine_bucket or "feminine_care_daily_liner",
            recommended_collab_type=COLLAB_SAMPLE,
            outreach_priority=P2,
            queue_type=QUEUE_FEMININE_WARM,
            recommendation_reason=(
                f"Medium feminine-care evidence (fit={fcf}). Profile data quality {dq} and "
                f"commercial value {cv} are good. Start with a low-cost sample test instead of manual review."
            ),
            next_action="Send a sample collab first; avoid paid budget until product-fit evidence improves.",
            risk_summary="medium_feminine_care_fit",
            review_required=False,
        )

    # --- 3. sample_collab_test_queue ---
    if (
        followers <= 100_000
        and (cv >= 70 or cs >= 85 or rd >= 75)
        and 20 <= primary_score <= 59
    ):
        priority = P2 if rd >= 75 and primary_score >= 40 else P3
        return Decision(
            recommendation_status=STATUS_LOW_COST_TEST,
            recommended_product_type=primary_cat if primary_score >= 40 else None,
            recommended_collab_type=COLLAB_GIFTED,
            outreach_priority=priority,
            queue_type=QUEUE_SAMPLE,
            recommendation_reason=(
                f"Small/mid creator ({followers:,} followers) with strong commercial/repeat signals (cv={cv}, commerce={cs}, repeat={rd}) "
                f"but only {primary_cat} fit at {primary_score}. Low-cost gifted review is the right test."
            ),
            next_action="Send a gifted product box and ask for one organic review video.",
            risk_summary="weak_to_medium_product_fit",
            review_required=False,
        )

    # --- 4. affiliate_test_queue ---
    if (cv >= 70 or cs >= 60 or rd >= 60) and primary_score < 60:
        priority = P2 if rd >= 75 and primary_score >= 40 else P3
        return Decision(
            recommendation_status=STATUS_AFFILIATE_TEST,
            recommended_product_type=primary_cat if primary_score >= 40 else None,
            recommended_collab_type=COLLAB_AFFILIATE,
            outreach_priority=priority,
            queue_type=QUEUE_AFFILIATE,
            recommendation_reason=(
                f"Commercial or repeat discovery value is strong (cv={cv}, commerce={cs}, repeat={rd}) but product fit ({primary_score}) is not high enough "
                f"to justify a paid collaboration. Commission-based outreach is the safer test."
            ),
            next_action="Offer an affiliate / commission-only collaboration with no upfront fee.",
            risk_summary="commercial_strong_but_product_fit_uncertain",
            review_required=False,
        )

    # --- 5. macro_brand_awareness_queue ---
    if followers >= 500_000 and primary_score < 40:
        return Decision(
            recommendation_status=STATUS_BRAND_AWARENESS_ONLY,
            recommended_product_type=None,
            recommended_collab_type=COLLAB_BRAND_AWARENESS,
            outreach_priority=P4,
            queue_type=QUEUE_MACRO,
            recommendation_reason=(
                f"Large creator ({followers:,} followers) but product fit is weak ({primary_score}). "
                f"Use only if a brand-awareness budget is available — not for conversion."
            ),
            next_action="Hold for brand awareness campaign, not conversion campaign.",
            risk_summary="macro_low_fit",
            review_required=False,
        )

    # --- 6. low_confidence_hold (other ambiguity) ---
    if score.evidence_strength == "weak" or score.content_format_status == "unknown":
        return Decision(
            recommendation_status=STATUS_HOLD,
            recommended_product_type=None,
            recommended_collab_type=COLLAB_DO_NOT_CONTACT,
            outreach_priority=P4,
            queue_type=QUEUE_LOW_CONFIDENCE_HOLD,
            recommendation_reason=(
                f"Evidence is weak (strength={score.evidence_strength}, content_format={score.content_format_status}). "
                f"The lead is held automatically until the collector finds clearer category evidence."
            ),
            next_action="Collect more profile/video evidence, then re-run the pipeline.",
            risk_summary="weak_category_evidence",
            review_required=False,
        )

    # --- 7. general_lifestyle_hold ---
    if primary_score < 40:
        return Decision(
            recommendation_status=STATUS_HOLD,
            recommended_product_type=None,
            recommended_collab_type=COLLAB_DO_NOT_CONTACT,
            outreach_priority=P4,
            queue_type=QUEUE_GENERAL_HOLD,
            recommendation_reason=(
                "No category reaches the 40-point fit threshold. The creator looks like a general "
                "lifestyle account — hold until a clearer signal appears."
            ),
            next_action="Watch the next batch of uploads for vertical signals.",
            risk_summary="low_product_fit",
            review_required=False,
        )

    # --- 8. not_recommended ---
    if primary_score < 20 and cv < 40:
        return Decision(
            recommendation_status=STATUS_NOT_RECOMMENDED,
            recommended_product_type=None,
            recommended_collab_type=COLLAB_DO_NOT_CONTACT,
            outreach_priority=P4,
            queue_type=QUEUE_NOT_RECOMMENDED,
            recommendation_reason="No clear product fit and low commercial value.",
            next_action="Do not contact now.",
            risk_summary="no_clear_fit; low_commercial_value",
            review_required=False,
        )

    # --- Default fallback: warm hold ---
    return Decision(
        recommendation_status=STATUS_HOLD,
        recommended_product_type=primary_cat if primary_score >= 40 else None,
        recommended_collab_type=COLLAB_GIFTED,
        outreach_priority=P3,
        queue_type=QUEUE_GENERAL_HOLD,
        recommendation_reason=(
            f"Mixed signals: product fit {primary_score} ({primary_cat}), commercial {cv}, content format "
            f"{score.content_format_status}. Default to a low-cost test if email is available."
        ),
        next_action="Send a small gifted product test if budget allows; otherwise wait for stronger signals.",
        risk_summary="mixed_signals",
        review_required=False,
    )
