from __future__ import annotations

from desktop.backend.services.xhs_lead_service import _metric_text
from desktop.backend.utils.xhs_cleaning import parse_count_text


def test_parse_count_text_does_not_join_full_profile_digits():
    text = (
        "AK 小红书号：5404742924 IP属地：河北 还没有简介 "
        "69 关注 309 粉丝 2635 获赞与收藏"
    )

    assert parse_count_text(text) is None
    assert parse_count_text(_metric_text(text, "", ("关注", "following"))) == 69
    assert parse_count_text(_metric_text(text, "", ("粉丝", "followers"))) == 309
    assert parse_count_text(_metric_text(text, "", ("获赞与收藏", "获赞", "likes"))) == 2635


def test_parse_count_text_handles_short_social_metrics_safely():
    assert parse_count_text("1.2w") == 12000
    assert parse_count_text("3.4万") == 34000
    assert parse_count_text("26061530352154375861419826922786681194848574528028672") is None
