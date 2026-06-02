from __future__ import annotations

from desktop.backend.utils.job_exclusion import check_excluded
from desktop.backend.utils.job_keyword_rules import score_company


def test_search_keyword_alone_does_not_create_company_tier():
    result = score_company(
        company_name="纯搜索词公司",
        search_keywords="跨境电商运营",
    )

    assert result["score"] < 40
    assert result["tier"] is None
    assert result["cooperation_type"] == "unknown"


def test_alibaba_international_station_merchant_is_not_excluded():
    hit, keyword = check_excluded(
        "广州乐信服饰有限公司",
        "乐信服饰是阿里巴巴国际站的金品商家，并享有平台资源。",
    )
    result = score_company(
        company_name="广州乐信服饰有限公司",
        industry="贸易/进出口",
        company_description="乐信服饰是阿里巴巴国际站的金品商家，并享有平台资源。",
        jd_titles=["外贸业务员"],
        search_keywords="外贸",
    )

    assert (hit, keyword) == (False, None)
    assert result["tier"] == "C"
    assert result["cooperation_type"] == "channel_partner"


def test_platform_operator_company_name_is_still_excluded():
    hit, keyword = check_excluded("阿里巴巴集团", "平台公司")

    assert hit is True
    assert keyword == "阿里巴巴"


def test_product_factory_is_capped_below_review_tier():
    result = score_company(
        company_name="星皇亚太企业（博罗）化工有限公司",
        industry="快速消费品(食品、饮料、化妆品)",
        company_description="主要生产化妆品等日用化工产品。",
        jd_titles=["电商运营"],
        search_keywords="跨境电商运营",
    )

    assert result["score"] < 40
    assert result["tier"] is None


def test_generic_trade_company_without_market_or_platform_stays_c_tier():
    result = score_company(
        company_name="浙江国恩物产有限公司",
        industry="石油/化工/矿产/地质",
        company_description="主营大宗商品及其制品的批发和零售，供应链服务商。",
        jd_titles=["外贸业务员/国际贸易专员"],
        search_keywords="外贸",
    )

    assert 40 <= result["score"] < 60
    assert result["tier"] == "C"
