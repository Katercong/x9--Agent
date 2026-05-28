"""Unit tests for the scoring + recommendation engines (no DB)."""
from __future__ import annotations

from x9_creator_desktop_system.backend.services.scoring_engine import compute_score
from x9_creator_desktop_system.backend.services.recommendation_engine import decide


def make(**overrides):
    base = {
        "platform": "tiktok",
        "search_keyword": "sanitary pads",
        "handle": "test",
        "display_name": "Test",
        "profile_url": "https://www.tiktok.com/@test",
        "bio": "lifestyle vlogger",
        "followers_count": 30_000,
        "likes_count": 100_000,
        "email": "test@gmail.com",
        "source_video_url": "https://www.tiktok.com/@test/video/1",
        "source_video_title": "haul: drugstore finds",
        "source_video_description": "showing my picks",
        "external_links": [],
        "hashtags": [],
        "repeat_discovery": {},
    }
    base.update(overrides)
    return base


def test_search_only_match_with_no_commerce_signal_routes_to_affiliate_test():
    s = compute_score(make(
        bio="just vibing",
        source_video_title="TikTok - Make Your Day",
        source_video_description=None,
    ))
    assert s.feminine_search_only_match is True
    assert s.commerce_signal_score < 70
    d = decide(s, followers=30_000, has_email=True)
    assert d.queue_type == "affiliate_test_queue"
    assert d.recommendation_status == "affiliate_test"
    assert d.review_required is False


def test_search_only_match_with_commerce_signal_routes_to_sample_test():
    """Commerce override: strong shop signals beat the manual-review hold."""
    s = compute_score(make(
        bio="amazon storefront, link in bio. discount code MINE10. tiktok shop affiliate.",
        source_video_title="amazon finds haul",
        source_video_description="my must haves with discount code",
    ))
    assert s.feminine_search_only_match is True
    assert s.commerce_signal_score >= 85
    d = decide(s, followers=30_000, has_email=True)
    assert d.queue_type == "sample_collab_test_queue"
    assert d.recommendation_status == "low_cost_test"
    assert d.review_required is False


def test_strong_feminine_evidence_recommends():
    s = compute_score(make(
        bio="period care reviews; menstrual care picks",
        source_video_title="my period routine",
    ))
    assert s.feminine_search_only_match is False
    assert s.primary_product_category == "feminine_care"
    d = decide(s, followers=30_000, has_email=True)
    assert d.queue_type == "feminine_conversion_queue"
    assert d.recommendation_status == "recommended"
    assert d.recommended_product_type is not None


def test_no_email_routes_to_no_contact_queue():
    s = compute_score(make(email=None))
    d = decide(s, followers=30_000, has_email=False)
    assert d.queue_type == "no_contact_info_queue"
    assert d.recommended_collab_type == "do_not_contact_now"


def test_macro_low_fit_routes_to_brand_awareness():
    s = compute_score(make(
        search_keyword="comedy",
        bio="comedy",
        followers_count=5_000_000,
        source_video_title="skit",
        source_video_description="lol",
    ))
    d = decide(s, followers=5_000_000, has_email=True)
    assert d.queue_type == "macro_brand_awareness_queue"
    assert d.recommended_collab_type == "brand_awareness_collab"


def test_audience_bonus_capped_at_10():
    s = compute_score(make(bio="new mom postpartum dog mom caregiver wellness home routine girl"))
    assert s.audience_fit_score <= 10


def test_contactability_uses_profile_description_contacts():
    s_no = compute_score(make(email=None, bio="business email pending"))
    assert s_no.contactability_score == 0
    assert s_no.has_contact is False
    s_whatsapp = compute_score(make(email=None, bio="WhatsApp 1234567890 for collabs. IG @creator.handle"))
    assert s_whatsapp.contactability_score == 80
    assert s_whatsapp.has_contact is True
    assert "whatsapp" in s_whatsapp.contact_types
    assert "instagram" in s_whatsapp.contact_types
    d = decide(s_whatsapp, followers=30_000, has_contact=s_whatsapp.has_contact)
    assert d.queue_type != "no_contact_info_queue"
    s_yes = compute_score(make(email="real@gmail.com"))
    assert s_yes.contactability_score == 100
    s_sus = compute_score(make(email="info@example.com"))
    assert s_sus.contactability_score == 50


def test_repeat_discovery_lifts_recommendation_score():
    """Same creator scored alone vs. with repeat-discovery context."""
    a = compute_score(make())
    b = compute_score(make(repeat_discovery={
        "unique_keyword_count": 3,
        "unique_video_count": 5,
        "same_keyword_extra_video_count": 2,
        "max_tag_support_count": 3,
        "commerce_observation_count": 3,
        "tag_boosts": {"feminine_care": 10},
    }))
    assert b.repeat_discovery_score > 0
    assert b.recommendation_score >= a.recommendation_score
    assert b.feminine_care_fit >= a.feminine_care_fit
